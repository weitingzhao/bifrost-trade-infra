#!/usr/bin/env bash
# Tests for research-user.sh with fake kubectl, curl and pbcopy: no cluster, no clipboard, no real token.
#   bash scripts/owner/research-user_test.sh
set -uo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
mkdir -p "$T/bin"
cat > "$T/bin/kubectl" <<'EOF'
#!/usr/bin/env bash
case "$*" in
  *"get secret"*) cat "$FAKE_SECRET" ;;
  *"patch secret"*) for a in "$@"; do [[ -f "$a" ]] && cp "$a" "$FAKE_LOG.patch"; done ;;
  *"rollout restart"*) echo "restart $*" >> "$FAKE_LOG" ;;
  *"rollout status"*) : ;;
esac
EOF
cat > "$T/bin/curl" <<'EOF'
#!/usr/bin/env bash
h=""; for a in "$@"; do case "$a" in @*) h=$(cat "${a#@}");; esac; done
echo "curl $*" >> "$FAKE_LOG"; [[ "$h" == "Authorization: Bearer "* ]] && printf 200 || printf 401
EOF
printf '#!/usr/bin/env bash\ncat > "$FAKE_LOG.clip"\n' > "$T/bin/pbcopy"
chmod +x "$T/bin/"*

fail=0
mk() { python3 -c 'import json,base64,sys; print(json.dumps({"data":{k:base64.b64encode(v.encode()).decode() for k,v in json.loads(sys.argv[1]).items()}}))' "$1" > "$T/secret-$2.json"; }
run() {
  local n="$1"; shift
  PATH="$T/bin:$PATH" KUBECONFIG="$T/kubeconfig" FAKE_SECRET="$T/secret-$n.json" FAKE_LOG="$T/log-$n" \
    bash "$here/research-user.sh" "$@" > "$T/out-$n" 2>&1
  echo $?
}
users_in_patch() { python3 -c 'import json,base64,sys; print(",".join(p.split(":")[0] for p in base64.b64decode(json.load(open(sys.argv[1]))["data"]["RESEARCH_USERS"]).decode().split(",")))' "$1"; }
check() { if eval "$2"; then echo "ok   $1"; else echo "FAIL $1"; fail=1; fi; }

mk '{"RESEARCH_API_TOKEN":"legacyTOK","RESEARCH_DEFAULT_OWNER":"vision"}' 1
rc=$(run 1 add spouse)
check "legacy token kept as a user, new user added" '[[ $rc == 0 && $(users_in_patch "$T/log-1.patch") == "vision,spouse" ]]'
check "the kept user still signs in" 'grep -q "vision still signs in: HTTP 200" "$T/out-1"'
check "research-api and research-mcp restarted, Dagster not" 'grep -q "deploy/research-api" "$T/log-1" && grep -q "deploy/research-mcp" "$T/log-1" && ! grep -q dagster "$T/log-1"'

mk '{"RESEARCH_USERS":"vision:aaa,bob:bbb"}' 2
rc=$(run 2 add spouse)
check "existing users kept in order" '[[ $rc == 0 && $(users_in_patch "$T/log-2.patch") == "vision,bob,spouse" ]]'
check "every existing user still signs in" 'grep -q "vision still signs in: HTTP 200" "$T/out-2" && grep -q "bob still signs in: HTTP 200" "$T/out-2"'
check "no token in curl arguments or output" '! grep -qE "aaa|bbb|legacyTOK|rsu_" "$T/log-1" "$T/log-2" "$T/out-1" "$T/out-2"'
check "the new token went to the clipboard" 'grep -q "^rsu_" "$T/log-2.clip"'

mk '{"RESEARCH_USERS":"vision:aaa,spouse:ccc"}' 3
rc=$(run 3 add spouse)
check "a duplicate user stops and patches nothing" '[[ $rc == 1 && ! -f "$T/log-3.patch" ]]'
rc=$(run 3 copy spouse)
check "copy puts the existing token on the clipboard" '[[ $rc == 0 && $(cat "$T/log-3.clip") == ccc && ! -f "$T/log-3.patch" ]]'

mk '{}' 4
rc=$(run 4 add spouse)
check "no sign-in configured: stop, nothing changed" '[[ $rc == 1 && ! -f "$T/log-4.patch" ]] && grep -q "Nothing changed" "$T/out-4"'

rc=$(run 4 add Spouse)
check "a bad user name stops" '[[ $rc == 1 ]]'

exit $fail
