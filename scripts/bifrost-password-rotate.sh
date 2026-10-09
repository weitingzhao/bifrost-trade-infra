#!/usr/bin/env bash
# Owner-run: rotate the password of Postgres role bifrost (TD-85 D5) in every place that carries it.
#
# bifrost is the owner of the Trade databases and of most of Golden Source. Since TD-85 the Trade runtime
# signs in as trade_app_<env>; bifrost's password is still held by (read-only 2026-10-04, names only):
#   data/bifrost-postgres-app                     password                 CNPG initdb.owner Secret. CNPG's
#                                                 instance manager re-applies it to the role whenever the
#                                                 Secret changes and on every primary start / failover,
#                                                 so it must end up holding the new value.
#   bifrost-<env>/bifrost-<env>-db-owner          PGPASSWORD, GOLDEN_SOURCE_PASSWORD   db-init Jobs
#   (the market-data / flex-query plugin Secrets left this list with TD-85 D6: they hold data_writer /
#    flex_writer since scripts/plugin-db-roles.sh switched them)
#   local gitignored files on this Mac            any value equal to the old password in the files
#                                                 listed by `holders` (.env of infra / plugins / research,
#                                                 k8s/base/secrets/*.yaml, k8s/data/secrets/*.yaml)
# The FDW user mappings store brokerage_reader / brokerage_writer passwords: not affected.
#
# Owner only. An Agent must not run this script.
# The old and new values live in ~/.bifrost-owner/owner.env (BIFROST_PG_PASSWORD_PREVIOUS / _NEXT).
# POSTGRES_PASSWORD stays in this repo's .env (TD-85). No
# subcommand prints a password; values travel on stdin or in mode-600 temp files removed on exit.
#
#   bifrost-password-rotate.sh holders           who holds the current value (yes / no per holder, from the
#                                                CNPG Secret), and live bifrost sessions per namespace
#   bifrost-password-rotate.sh ensure            BIFROST_PG_PASSWORD_PREVIOUS := the CNPG Secret's value (if
#                                                unset), BIFROST_PG_PASSWORD_NEXT := new random (if unset)
#   bifrost-password-rotate.sh rotate [--any-time]
#                                                preflight, then: 1 every non-CNPG Secret -> NEXT (running pods
#                                                keep their env); 2 ALTER ROLE bifrost PASSWORD <SCRAM verifier
#                                                of NEXT> (the cut-over); 3 CNPG Secret -> NEXT; 4 restart the
#                                                Deployments that mount a holder Secret; 5 local files: every
#                                                value equal to PREVIOUS -> NEXT; 6 check
#   bifrost-password-rotate.sh rollback          the same five moves back to PREVIOUS
#   bifrost-password-rotate.sh check             NEXT / PREVIOUS sign in? every holder equal to NEXT? sessions
#
# rotate refuses during the market-data batch window (weekdays 20:55-23:30 UTC) and while a db-init Job is
# running, unless --any-time is given. Plan and order: scripts/release/db-steps.d/2026-10-04-d5-bifrost-password-rotate.md.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORKSPACE="${BIFROST_WORKSPACE:-$(cd "$ROOT/.." && pwd)}"
ENV_FILE="${BIFROST_ROTATE_ENV:-${BIFROST_OWNER_ENV:-${HOME}/.bifrost-owner/owner.env}}"
OWNER_SECRETS="${BIFROST_OWNER_SECRETS:-${HOME}/.bifrost-owner/secrets}"
export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}"
KEY_PREV=BIFROST_PG_PASSWORD_PREVIOUS
KEY_NEXT=BIFROST_PG_PASSWORD_NEXT
CNPG_NS=data
CNPG_SECRET=bifrost-postgres-app
# namespace/secret:key[,key] — every Kubernetes holder except CNPG's own Secret.
HOLDERS=(
  bifrost-dev/bifrost-dev-db-owner:PGPASSWORD,GOLDEN_SOURCE_PASSWORD
  bifrost-stg/bifrost-stg-db-owner:PGPASSWORD,GOLDEN_SOURCE_PASSWORD
  bifrost-prod/bifrost-prod-db-owner:PGPASSWORD,GOLDEN_SOURCE_PASSWORD
)
# Gitignored local files that may carry the value (KEY=value or YAML key: value lines).
LOCAL_FILES=(
  "$ROOT/.env"
  "$ENV_FILE"
  "$OWNER_SECRETS/bifrost-dev-db-owner.yaml"
  "$OWNER_SECRETS/bifrost-stg-db-owner.yaml"
  "$OWNER_SECRETS/bifrost-prod-db-owner.yaml"
  "$OWNER_SECRETS/bifrost-dev-secrets.yaml"
  "$OWNER_SECRETS/bifrost-stg-secrets.yaml"
  "$OWNER_SECRETS/bifrost-prod-secrets.yaml"
  "$ROOT/k8s/base/secrets/bifrost-dev-db-owner.yaml"
  "$ROOT/k8s/base/secrets/bifrost-stg-db-owner.yaml"
  "$ROOT/k8s/base/secrets/bifrost-prod-db-owner.yaml"
  "$ROOT/k8s/base/secrets/bifrost-dev-secrets.yaml"
  "$ROOT/k8s/base/secrets/bifrost-stg-secrets.yaml"
  "$ROOT/k8s/base/secrets/bifrost-prod-secrets.yaml"
  "$ROOT/k8s/data/secrets/bifrost-postgres-app.yaml"
  "$WORKSPACE/bifrost-platform-plugin-market-data/.env"
  "$WORKSPACE/bifrost-platform-plugin-flex-query/.env"
  "$WORKSPACE/bifrost-research/.env"
)

# BIFROST_ROTATE_LOCAL_FILES (colon-separated) replaces the list above (rehearsal only).
if [[ -n "${BIFROST_ROTATE_LOCAL_FILES:-}" ]]; then IFS=: read -r -a LOCAL_FILES <<<"$BIFROST_ROTATE_LOCAL_FILES"; fi

rotate_help() { sed -n '2,36p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }
fail() { echo "ERROR: $*" >&2; exit 1; }

SCRATCH=()
trap 'rm -f "${SCRATCH[@]:-}"' EXIT
private_tmp() {  # private_tmp VAR: a mode-600 temp file, removed on exit
  local f
  f="$(mktemp)"
  chmod 600 "$f"
  SCRATCH+=("$f")
  printf -v "$1" '%s' "$f"
}

primary_pod() {
  local p
  p="$(kubectl -n data get cluster bifrost-postgres -o jsonpath='{.status.currentPrimary}' 2>/dev/null || true)"
  echo "${p:-bifrost-postgres-1}"
}
# BIFROST_ROTATE_DB_EXEC replaces the kubectl exec prefix (rehearsal against a local container only).
in_db() {
  if [[ -n "${BIFROST_ROTATE_DB_EXEC:-}" ]]; then
    local pre
    read -r -a pre <<<"$BIFROST_ROTATE_DB_EXEC"
    "${pre[@]}" "$@"
  else
    kubectl -n data exec -i "$(primary_pod)" -c postgres -- "$@"
  fi
}

# env_value KEY: the .env value on stdout (pipe only); exit 1 when unset.
env_value() {
  python3 - "$ENV_FILE" "$1" <<'PY'
import re, sys
path, key = sys.argv[1], sys.argv[2]
try:
    text = open(path, encoding="utf-8").read()
except FileNotFoundError:
    text = ""
m = re.search(rf"^{key}=(.*)$", text, flags=re.M)
val = m.group(1).strip().strip('"').strip("'") if m else ""
if not val:
    sys.exit(f"{key} is not set in {path}; run: scripts/bifrost-password-rotate.sh ensure")
sys.stdout.write(val)
PY
}

# secret_value NS NAME KEY: one decoded field on stdout (pipe only); exit 1 when absent.
secret_value() {
  kubectl -n "$1" get secret "$2" -o json 2>/dev/null | python3 -c '
import base64, json, sys
raw = sys.stdin.read()
v = ((json.loads(raw).get("data") or {}).get(sys.argv[1]) if raw.strip() else None)
if not v:
    sys.exit(1)
sys.stdout.write(base64.b64decode(v).decode())
' "$3"
}

# same_value: two values on stdin separated by one NUL; prints yes / no / missing.
same_value() {
  python3 -c '
import sys
a, _, b = sys.stdin.buffer.read().partition(b"\0")
print("missing" if not b else ("yes" if a and a == b else "no"))
'
}
holder_equals() {  # holder_equals NS NAME KEY ENVKEY -> yes / no / missing
  { env_value "$4" 2>/dev/null || true; printf '\0'; secret_value "$1" "$2" "$3" 2>/dev/null || true; } | same_value
}
cnpg_equals() {  # cnpg_equals NS NAME KEY -> is that field equal to the CNPG Secret's password? yes / no / missing
  { secret_value "$CNPG_NS" "$CNPG_SECRET" password 2>/dev/null || true; printf '\0'; secret_value "$1" "$2" "$3" 2>/dev/null || true; } | same_value
}

# signs_in_as_bifrost DB: password on stdin, TCP login inside the database pod.
signs_in_as_bifrost() {
  in_db sh -c 'IFS= read -r PGPASSWORD || true; export PGPASSWORD
    psql -h localhost -U bifrost -d "$0" -X -tAc "SELECT 1" >/dev/null 2>&1' "$1"
}
answer() { if "$@"; then echo yes; else echo no; fi; }

# set_holder NS NAME KEYS(comma): value on stdin -> patch those keys (stringData), nothing printed.
set_holder() {
  local patch
  private_tmp patch
  python3 -c '
import json, sys
keys, out = sys.argv[1].split(","), sys.argv[2]
pw = sys.stdin.read()
if not pw:
    sys.exit("no value on stdin; nothing changed")
json.dump({"stringData": {k: pw for k in keys}}, open(out, "w"))
' "$3" "$patch"
  kubectl -n "$1" patch secret "$2" --type merge --patch-file "$patch" >/dev/null
  echo "  $1/$2: $3 updated (value omitted)"
}

# set_role_password: value on stdin -> ALTER ROLE bifrost with a SCRAM-SHA-256 verifier computed here.
set_role_password() {
  python3 -c '
import base64, hashlib, hmac, os, sys
pw = sys.stdin.read().encode()
if not pw:
    sys.exit("no value on stdin")
salt, it = os.urandom(16), 4096
salted = hashlib.pbkdf2_hmac("sha256", pw, salt, it)
ck = hmac.new(salted, b"Client Key", "sha256").digest()
sk = hmac.new(salted, b"Server Key", "sha256").digest()
b = lambda x: base64.b64encode(x).decode()
print("\\set ON_ERROR_STOP on")
print(f"ALTER ROLE bifrost PASSWORD $v$SCRAM-SHA-256${it}:{b(salt)}${b(hashlib.sha256(ck).digest())}:{b(sk)}$v$;")
' | in_db psql -U postgres -d postgres -X -q
  echo "  role bifrost: password set (SCRAM verifier only)"
}

# replace_local FROM_KEY TO_KEY: in every local file, a value equal to .env FROM_KEY becomes TO_KEY's.
# Only whole values are replaced (KEY=value, KEY: value, KEY: "value"); counts are printed, values never.
replace_local() {
  local pairs
  private_tmp pairs
  { env_value "$1"; printf '\0'; env_value "$2"; } >"$pairs"
  python3 - "$pairs" "$ENV_FILE" "$1" "$2" "${LOCAL_FILES[@]}" <<'PY'
import os, re, sys
pairs, env_file, from_key, to_key, *files = sys.argv[1:]
old, _, new = open(pairs, "rb").read().decode().partition("\0")
if not old or not new:
    sys.exit("missing value")
for path in files:
    if not os.path.isfile(path):
        continue
    text = open(path, encoding="utf-8").read()
    n = 0
    def sub(m):
        global n
        key = m.group(1)
        if os.path.abspath(path) == os.path.abspath(env_file) and key in (from_key, to_key):
            return m.group(0)
        q = m.group(3) or ""
        if m.group(4) != old:
            return m.group(0)
        n += 1
        return f"{m.group(1)}{m.group(2)}{q}{new}{q}"
    text2 = re.sub(r'^([ \t]*[A-Za-z_][A-Za-z0-9_.-]*)([ \t]*[=:][ \t]*)(["\']?)(.*?)\3[ \t]*$', sub, text, flags=re.M)
    if n:
        mode = os.stat(path).st_mode & 0o777
        open(path, "w", encoding="utf-8").write(text2)
        os.chmod(path, mode)
    print(f"  {path}: {n} value(s) replaced")
PY
}

# Deployments (any namespace) whose pods take a holder Secret; db-init Jobs pick the new value on their next run.
holder_deployments() {
  kubectl get deploy -A -o json | python3 -c '
import json, sys
pairs = [a.split("/", 1) for a in sys.argv[1:]]
for d in json.load(sys.stdin)["items"]:
    s = json.dumps(d["spec"]["template"]["spec"])
    ns = d["metadata"]["namespace"]
    if any(ns == hns and json.dumps(hname) in s for hns, hname in pairs):
        print(ns, d["metadata"]["name"])
' "${HOLDERS[@]%%:*}"
}

restart_holders() {
  local ns name
  holder_deployments | while read -r ns name; do
    kubectl -n "$ns" rollout restart "deploy/$name" >/dev/null && echo "  restarted $ns/$name"
  done
  holder_deployments | while read -r ns name; do
    kubectl -n "$ns" rollout status "deploy/$name" --timeout=300s >/dev/null && echo "  ready $ns/$name"
  done
}

sessions_by_namespace() {
  echo "bifrost sessions by client namespace (pod IPs of Running pods; 'local' = in the database pod):"
  local ips
  private_tmp ips
  kubectl get pods -A --field-selector=status.phase=Running \
    -o jsonpath='{range .items[*]}{.status.podIP} {.metadata.namespace}{"\n"}{end}' >"$ips"
  in_db psql -U postgres -d postgres -X -tA -F' ' -c "SET default_transaction_read_only=on;" -c "
    SELECT coalesce(host(client_addr), 'local'), datname, min(backend_start)::timestamp(0)
      FROM pg_stat_activity WHERE usename = 'bifrost' GROUP BY 1, 2;" | { grep -v '^SET$' || true; } |
    python3 -c '
import sys, collections
ns = dict(l.split() for l in open(sys.argv[1]) if len(l.split()) == 2)
agg = collections.defaultdict(lambda: [0, None])
for line in sys.stdin:
    p = line.split()
    if len(p) < 4:
        continue
    key = (ns.get(p[0], "local" if p[0] == "local" else "unknown:" + p[0]), p[1])
    agg[key][0] += 1
    agg[key][1] = min(filter(None, [agg[key][1], p[2] + " " + p[3]]))
for (n, db), (c, t) in sorted(agg.items()):
    print(f"  {n:<22} {db:<24} clients={c} oldest={t}")
' "$ips"
}

check_window() {
  python3 - <<'PY'
import datetime, sys
now = datetime.datetime.now(datetime.timezone.utc)
mins = now.hour * 60 + now.minute
busy = now.weekday() < 5 and 20 * 60 + 55 <= mins < 23 * 60 + 30
sys.exit(1 if busy else 0)
PY
}

db_init_running() {
  local e
  for e in dev stg prod; do
    [[ "$(kubectl -n "bifrost-$e" get job "db-init-$e" -o jsonpath='{.status.active}' 2>/dev/null || true)" == "" ]] || return 0
  done
  return 1
}

preflight() {  # preflight FROM_KEY: every holder equals FROM_KEY's value, FROM_KEY signs in
  local from="$1" h ns name keys k bad=0
  env_value "$KEY_PREV" >/dev/null
  env_value "$KEY_NEXT" >/dev/null
  { env_value "$KEY_PREV"; printf '\0'; env_value "$KEY_NEXT"; } | python3 -c '
import sys
a, _, b = sys.stdin.buffer.read().partition(b"\0")
sys.exit("PREVIOUS and NEXT are equal; run ensure after clearing NEXT" if a == b else 0)'
  env_value "$from" | signs_in_as_bifrost bifrost_golden_source || fail "the local $from does not sign in as bifrost; nothing changed"
  [[ "$(holder_equals "$CNPG_NS" "$CNPG_SECRET" password "$from")" == yes ]] || bad=1
  for h in "${HOLDERS[@]}"; do
    ns="${h%%/*}"; name="${h#*/}"; name="${name%%:*}"; keys="${h##*:}"
    for k in ${keys//,/ }; do
      [[ "$(holder_equals "$ns" "$name" "$k" "$from")" == yes ]] || { echo "  $ns/$name $k is not the $from value" >&2; bad=1; }
    done
  done
  for e in dev stg prod; do
    [[ "$(secret_value "bifrost-$e" "bifrost-$e-secrets" PGUSER 2>/dev/null || echo bifrost)" != bifrost ]] ||
      { echo "  bifrost-$e/bifrost-$e-secrets still signs the Trade runtime in as bifrost (TD-85 switch / rollback?)" >&2; bad=1; }
  done
  [[ $bad -eq 0 ]] || fail "holders disagree (above); nothing changed. Run: $0 holders"
}

move_all() {  # move_all FROM_KEY TO_KEY
  local from="$1" to="$2" h ns name keys
  echo "1. holder Secrets -> $to (running pods keep their env until restarted)"
  for h in "${HOLDERS[@]}"; do
    ns="${h%%/*}"; name="${h#*/}"; name="${name%%:*}"; keys="${h##*:}"
    env_value "$to" | set_holder "$ns" "$name" "$keys"
  done
  echo "2. the cut-over"
  env_value "$to" | set_role_password
  echo "3. CNPG Secret -> $to (its instance manager re-applies the same value)"
  env_value "$to" | set_holder "$CNPG_NS" "$CNPG_SECRET" password
  echo "4. restart the Deployments that mount a holder Secret"
  restart_holders
  echo "5. local files"
  replace_local "$from" "$to"
}

show_check() {
  local h ns name keys k
  echo "local $KEY_NEXT signs in as bifrost: $(env_value "$KEY_NEXT" 2>/dev/null | answer signs_in_as_bifrost bifrost_golden_source)"
  echo "local $KEY_PREV signs in as bifrost: $(env_value "$KEY_PREV" 2>/dev/null | answer signs_in_as_bifrost bifrost_golden_source)"
  echo "$CNPG_NS/$CNPG_SECRET password = NEXT: $(holder_equals "$CNPG_NS" "$CNPG_SECRET" password "$KEY_NEXT")"
  for h in "${HOLDERS[@]}"; do
    ns="${h%%/*}"; name="${h#*/}"; name="${name%%:*}"; keys="${h##*:}"
    for k in ${keys//,/ }; do echo "$ns/$name $k = NEXT: $(holder_equals "$ns" "$name" "$k" "$KEY_NEXT")"; done
  done
  sessions_by_namespace
}

cmd="${1:-}"
[[ -n "$cmd" ]] || rotate_help
shift

case "$cmd" in
holders)
  echo "Kubernetes holders: equal to the CNPG Secret's password (the role's source of truth)?"
  echo "  $CNPG_NS/$CNPG_SECRET password: (reference)"
  for h in "${HOLDERS[@]}"; do
    ns="${h%%/*}"; name="${h#*/}"; name="${name%%:*}"; keys="${h##*:}"
    for k in ${keys//,/ }; do echo "  $ns/$name $k: $(cnpg_equals "$ns" "$name" "$k")"; done
  done
  for e in dev stg prod; do
    echo "  bifrost-$e/bifrost-$e-secrets signs the runtime in as: $(secret_value "bifrost-$e" "bifrost-$e-secrets" PGUSER 2>/dev/null || echo 'bifrost (no PGUSER)')"
  done
  echo "Deployments that will be restarted:"
  holder_deployments | sed 's/^/  /'
  echo "Local files (count of values equal to the CNPG Secret's password):"
  ref=""
  private_tmp ref
  secret_value "$CNPG_NS" "$CNPG_SECRET" password >"$ref" || fail "cannot read $CNPG_NS/$CNPG_SECRET"
  python3 - "$ref" "${LOCAL_FILES[@]}" <<'PY'
import os, re, sys
ref = open(sys.argv[1]).read()
for path in sys.argv[2:]:
    if not os.path.isfile(path):
        print(f"  {path}: absent")
        continue
    keys = [m.group(1).strip() for m in re.finditer(r'^([ \t]*[A-Za-z_][A-Za-z0-9_.-]*)[ \t]*[=:][ \t]*(["\']?)(.*?)\2[ \t]*$', open(path, encoding="utf-8").read(), flags=re.M) if m.group(3) == ref]
    print(f"  {path}: {len(keys)}" + (f" ({', '.join(keys)})" if keys else ""))
PY
  sessions_by_namespace
  ;;

ensure)
  [[ -f "$ENV_FILE" ]] || (umask 077 && : >"$ENV_FILE")
  if ! env_value "$KEY_PREV" >/dev/null 2>&1; then
    secret_value "$CNPG_NS" "$CNPG_SECRET" password | python3 -c '
import sys
path, key = sys.argv[1], sys.argv[2]
v = sys.stdin.read()
if not v:
    sys.exit("empty CNPG Secret value")
t = open(path, encoding="utf-8").read()
open(path, "a", encoding="utf-8").write(("" if not t or t.endswith("\n") else "\n") + f"{key}={v}\n")
' "$ENV_FILE" "$KEY_PREV"
    echo "saved the current value as $KEY_PREV in $ENV_FILE (value omitted)"
  else
    echo "$KEY_PREV already set; left as is"
  fi
  if ! env_value "$KEY_NEXT" >/dev/null 2>&1; then
    python3 -c '
import secrets, sys
path, key = sys.argv[1], sys.argv[2]
t = open(path, encoding="utf-8").read()
open(path, "a", encoding="utf-8").write(("" if not t or t.endswith("\n") else "\n") + f"{key}={secrets.token_urlsafe(32)}\n")
' "$ENV_FILE" "$KEY_NEXT"
    echo "generated $KEY_NEXT into $ENV_FILE (value omitted)"
  else
    echo "$KEY_NEXT already set; left as is"
  fi
  ;;

rotate)
  if [[ "${1:-}" != --any-time ]]; then
    check_window || fail "inside the market-data batch window (weekdays 20:55-23:30 UTC); pass --any-time to override"
    ! db_init_running || fail "a db-init Job is running; wait for it"
  fi
  preflight "$KEY_PREV"
  move_all "$KEY_PREV" "$KEY_NEXT"
  echo "6. check"
  show_check
  echo "done. Old value stays in $ENV_FILE as $KEY_PREV for rollback; remove it once the next db-init and a plugin day passed."
  ;;

rollback)
  env_value "$KEY_PREV" >/dev/null
  move_all "$KEY_NEXT" "$KEY_PREV"
  echo "rolled back. Now: $0 check (PREVIOUS should sign in, NEXT should not)"
  ;;

check)
  show_check
  ;;

*)
  rotate_help
  ;;
esac
