#!/usr/bin/env bash
# Stub curl. Does not call the cluster or the platform.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="${ROOT}/owner-run.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export HOME="${TMP}/home"
export PLATFORM_PROD_VIEWER_TOKEN="viewer-token"
export PLATFORM_OWNER_RUN_TOKEN="run-token"
export PLATFORM_API="http://platform.test"
export ENV_FILE="${TMP}/no.env"
export OWNER_KUBECONFIG="${TMP}/kubeconfig"
export OWNER_RUN_MAX_AGE_SECONDS=86400
export APPROVAL_RESULT_RETRY_SECONDS=0
export CURL_LOG="${TMP}/curl.log"
touch "$OWNER_KUBECONFIG"
mkdir -p "${HOME}/bin"
cat > "${HOME}/bin/curl" <<'EOF'
#!/usr/bin/env python3
# GET prints $CURL_BODY. POST writes $FAKE_<KIND>_JSON to -o and prints
# $FAKE_<KIND>_CODE (default 200). Every call is logged to $CURL_LOG.
import json, os, re, sys
args = sys.argv[1:]
url = config = data = out = ""
i = 0
while i < len(args):
    a = args[i]
    if a in ("--config", "--url", "--data-binary", "-o", "-w", "-H") and i + 1 < len(args):
        value = args[i + 1]
        if a == "--config": config = value
        elif a == "--url": url = value
        elif a == "--data-binary": data = value
        elif a == "-o": out = value
        i += 2
        continue
    i += 1
token = ""
if config:
    m = re.search(r"Bearer ([^\"]*)", open(config).read())
    token = m.group(1) if m else ""
body = open(data[1:]).read() if data.startswith("@") else ""
kind = "get"
for k in ("claim", "heartbeat", "result"):
    if url.endswith("/" + k):
        kind = k
with open(os.environ["CURL_LOG"], "a") as fh:
    fh.write(json.dumps({"kind": kind, "url": url, "token": token, "data": body}) + "\n")
if kind == "get":
    sys.stdout.write(os.environ.get("CURL_BODY", ""))
    sys.exit(0)
with open(out, "w") as fh:
    fh.write(os.environ.get("FAKE_%s_JSON" % kind.upper(), "{}"))
sys.stdout.write(os.environ.get("FAKE_%s_CODE" % kind.upper(), "200"))
EOF
chmod +x "${HOME}/bin/curl" "$SCRIPT"
export PATH="${HOME}/bin:${PATH}"

sha() { printf '%s' "$1" | shasum -a 256 | awk '{print $1}'; }

fail_if_runs() {
  local name="$1"
  if "$SCRIPT" "$name" </dev/null >"${TMP}/out" 2>"${TMP}/err"; then
    echo "FAIL ${name} was accepted" >&2
    cat "${TMP}/err" >&2
    exit 1
  fi
}

# run_tty ANSWER ARG... runs the script on a pseudo-terminal and types ANSWER.
run_tty() {
  python3 - "$SCRIPT" "$@" <<'PY'
import os, pty, subprocess, sys
script, answer, args = sys.argv[1], sys.argv[2], sys.argv[3:]
tmp = os.environ["TMP_DIR"]
master, slave = pty.openpty()
with open(os.path.join(tmp, "out"), "w") as out, open(os.path.join(tmp, "err"), "w") as err:
    proc = subprocess.Popen(["bash", script] + args, stdin=slave, stdout=out, stderr=err)
    os.close(slave)
    os.write(master, (answer + "\n").encode())
    rc = proc.wait(timeout=60)
os.close(master)
sys.exit(rc)
PY
}
export TMP_DIR="$TMP"

CMD_TRUE="true"
H_TRUE="$(sha "$CMD_TRUE")"

export CURL_BODY='{"action":"rolling_reboot","status":"approved","runner":"owner","execution":{"deadline":"2099-01-01T00:00:00Z"},"params":{"command":"true"},"result":{"command_sha256":"'"$H_TRUE"'"}}'
fail_if_runs wrong-action
grep -q "want owner_run_command approved" "${TMP}/err"

export CURL_BODY='{"action":"owner_run_command","status":"pending","params":{"command":"true"},"result":{"command_sha256":"x"}}'
fail_if_runs wrong-status
grep -q "status=pending" "${TMP}/err"

for state in running unknown failed; do
  export CURL_BODY='{"action":"owner_run_command","status":"'"$state"'","runner":"owner","execution":{"deadline":"2099-01-01T00:00:00Z"},"params":{"command":"true"},"result":{"command_sha256":"'"$H_TRUE"'"}}'
  fail_if_runs "state-${state}"
  grep -q "status=${state}" "${TMP}/err"
done

export CURL_BODY='{"action":"owner_run_command","status":"executed","decided_at":"2020-01-01T00:00:00Z","params":{"command":"true"},"result":{"command_sha256":"'"$H_TRUE"'"}}'
fail_if_runs expired
grep -q "older than" "${TMP}/err"

export CURL_BODY='{"action":"owner_run_command","status":"approved","runner":"owner","execution":{"deadline":"2020-01-01T00:00:00Z"},"params":{"command":"true"},"result":{"command_sha256":"'"$H_TRUE"'"}}'
fail_if_runs past-deadline
grep -q "past its execution deadline" "${TMP}/err"

export CURL_BODY='{"action":"owner_run_command","status":"approved","runner":"host","execution":{"deadline":"2099-01-01T00:00:00Z"},"params":{"command":"true"},"result":{"command_sha256":"'"$H_TRUE"'"}}'
fail_if_runs host-runner
grep -q "runner=host" "${TMP}/err"

export CURL_BODY='{"action":"owner_run_command","status":"approved","runner":"owner","execution":{"deadline":"2099-01-01T00:00:00Z"},"params":{"command":"true"},"result":{"command_sha256":"deadbeef"}}'
fail_if_runs bad-hash
grep -q "hash does not match" "${TMP}/err"

fail_if_runs 'bad ref'
grep -q "one id or #n" "${TMP}/err"

export CURL_BODY='{"action":"owner_run_command","status":"approved","runner":"owner","execution":{"deadline":"2099-01-01T00:00:00Z"},"params":{"command":"true"},"result":{"command_sha256":"'"$H_TRUE"'"}}'
if printf 'yes\n' | "$SCRIPT" piped >"${TMP}/out" 2>"${TMP}/err"; then
  echo "FAIL piped yes was accepted" >&2
  exit 1
fi
grep -q "standard input must be a terminal" "${TMP}/err"

# Claim, run, post the result: #57 resolves to its id, exit 3 is recorded.
MARK="${TMP}/ran"
CMD_RUN="echo hello-from-owner-run; touch ${MARK}; exit 3"
export CURL_BODY='{"id":"appr_57","number":57,"action":"owner_run_command","status":"approved","runner":"owner","execution":{"deadline":"2099-01-01T00:00:00Z"},"params":{"command":"'"$CMD_RUN"'"},"result":{"command_sha256":"'"$(sha "$CMD_RUN")"'"}}'
export FAKE_CLAIM_JSON='{"lease_id":"lease_0123abcd0123abcd0123abcd","approval":{}}'
: > "$CURL_LOG"
set +e
run_tty yes '#57'
rc=$?
set -e
if [ "$rc" -ne 3 ]; then
  echo "FAIL claim run exited ${rc}, want 3" >&2
  cat "${TMP}/err" >&2
  exit 1
fi
[ -f "$MARK" ] || { echo "FAIL the command did not run" >&2; exit 1; }
grep -q "approval #57" "${TMP}/out"
python3 - "$CURL_LOG" "${HOME}/.bifrost-owner" <<'PY'
import hashlib, json, os, stat, sys
calls = [json.loads(line) for line in open(sys.argv[1])]
kinds = [c["kind"] for c in calls]
assert kinds[0] == "get" and calls[0]["url"].endswith("/api/v1/approvals/57"), calls[0]
assert calls[0]["token"] == "viewer-token", "the read uses the viewer token"
claim = [c for c in calls if c["kind"] == "claim"]
assert len(claim) == 1, kinds
assert claim[0]["token"] == "run-token", "the claim uses the run token"
body = json.loads(claim[0]["data"])
assert body["id"] == "appr_57" and body["runners"] == ["owner"], body
result = [c for c in calls if c["kind"] == "result"]
assert len(result) == 1 and result[0]["url"].endswith("/approvals/appr_57/result"), kinds
posted = json.loads(result[0]["data"])
assert posted["lease_id"] == "lease_0123abcd0123abcd0123abcd" and posted["started"] is True and posted["exit_code"] == 3, posted
assert "hello-from-owner-run" in posted["output_tail"], posted
assert len(posted["output_tail"].encode()) <= 2048
owner = sys.argv[2]
out = os.path.join(owner, "run-output", "appr_57.log")
raw = open(out, "rb").read()
assert posted["output_sha256"] == hashlib.sha256(raw).hexdigest()
assert stat.S_IMODE(os.stat(out).st_mode) == 0o600, oct(os.stat(out).st_mode)
row = json.loads(open(os.path.join(owner, "run-log.jsonl")).read().splitlines()[-1])
assert row["id"] == "appr_57" and row["ref"] == "#57" and row["exit"] == 3 and row["result_posted"] is True, row
PY
if grep -q "run-token\|viewer-token" "${TMP}/out" "${TMP}/err"; then
  echo "FAIL a token reached the terminal" >&2
  exit 1
fi

# A second run (or another session) holding the claim: refused, nothing runs.
rm -f "$MARK"
export FAKE_CLAIM_CODE=409
export FAKE_CLAIM_JSON='{"error":"not claimable","status":"running"}'
: > "$CURL_LOG"
if run_tty yes appr_57; then
  echo "FAIL a refused claim still ran" >&2
  exit 1
fi
grep -q "could not claim approval appr_57 (HTTP 409)" "${TMP}/err"
[ ! -f "$MARK" ] || { echo "FAIL the command ran without a claim" >&2; exit 1; }
if grep -q '"kind": "result"' "$CURL_LOG"; then
  echo "FAIL a result was posted without a claim" >&2
  exit 1
fi
unset FAKE_CLAIM_CODE

# The result post failing does not change the exit code; the run log says so.
export FAKE_CLAIM_JSON='{"lease_id":"lease_0123abcd0123abcd0123abcd","approval":{}}'
export FAKE_RESULT_CODE=503
CMD_OK="touch ${MARK}"
export CURL_BODY='{"id":"appr_58","number":58,"action":"owner_run_command","status":"approved","runner":"owner","execution":{"deadline":"2099-01-01T00:00:00Z"},"params":{"command":"'"$CMD_OK"'"},"result":{"command_sha256":"'"$(sha "$CMD_OK")"'"}}'
: > "$CURL_LOG"
run_tty yes 58
grep -q "could not post the result of approval appr_58 (HTTP 503)" "${TMP}/err"
[ "$(grep -c '"kind": "result"' "$CURL_LOG")" = "3" ]
tail -1 "${HOME}/.bifrost-owner/run-log.jsonl" | grep -q '"result_posted": false'
unset FAKE_RESULT_CODE

# A record from before the claim protocol still runs, without a claim.
rm -f "$MARK"
export CURL_BODY='{"id":"appr_old","action":"owner_run_command","status":"executed","decided_at":"2099-01-01T00:00:00Z","params":{"command":"'"$CMD_OK"'"},"result":{"command_sha256":"'"$(sha "$CMD_OK")"'"}}'
: > "$CURL_LOG"
run_tty yes appr_old
[ -f "$MARK" ] || { echo "FAIL the legacy record did not run" >&2; exit 1; }
grep -q "predates the claim protocol" "${TMP}/err"
if grep -q '"kind": "claim"\|"kind": "result"' "$CURL_LOG"; then
  echo "FAIL the legacy record was claimed" >&2
  exit 1
fi

# Typing anything but yes runs nothing and claims nothing.
rm -f "$MARK"
export CURL_BODY='{"id":"appr_58","number":58,"action":"owner_run_command","status":"approved","runner":"owner","execution":{"deadline":"2099-01-01T00:00:00Z"},"params":{"command":"'"$CMD_OK"'"},"result":{"command_sha256":"'"$(sha "$CMD_OK")"'"}}'
: > "$CURL_LOG"
if run_tty no 58; then
  echo "FAIL no was accepted" >&2
  exit 1
fi
[ ! -f "$MARK" ]
if grep -q '"kind": "claim"' "$CURL_LOG"; then
  echo "FAIL a claim was made without yes" >&2
  exit 1
fi

echo "ok: owner-run claims approved records once, posts exit code, hash and tail, refuses other states, a held claim, a hash mismatch and a piped yes, and still runs legacy executed records"
