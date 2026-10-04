#!/usr/bin/env bash
# Owner-run: the two Ops plugins sign in to Postgres as their own roles instead of bifrost (TD-85 D6, P1):
#   market-data  -> data_writer  (Secret plugin-market-data/market-data-secrets: postgres-user, postgres-password)
#   flex         -> flex_writer  (Secret plugin-flex-query/flex-query-secrets: postgres-user, postgres-password,
#                                 trade-pg-password)
# The plugins read the login from the Secret key postgres-user from market-data 0.76.0 / flex-query 0.9.0 on
# (optional key: without it they keep the ConfigMap's user, bifrost). So a switch and its rollback are each
# one Secret patch plus a restart.
#
# Passwords live in this repo's gitignored .env (DATA_WRITER_PG_PASSWORD, FLEX_WRITER_PG_PASSWORD) and in the
# Secrets. No subcommand prints one; they travel on stdin or in mode-600 temp files removed on exit, never on a
# command line (not in shell history, not in `ps`). bifrost's password for a rollback is read from CNPG's
# Secret data/bifrost-postgres-app (the role's source of truth since D5), never stored here.
#
#   plugin-db-roles.sh ensure                      generate the missing DATA_WRITER_PG_PASSWORD /
#                                                  FLEX_WRITER_PG_PASSWORD into .env
#   plugin-db-roles.sh password data_writer|flex_writer
#                                                  set the role's password: a SCRAM-SHA-256 verifier is computed
#                                                  here and sent; the password never reaches Postgres or its logs
#   plugin-db-roles.sh switch market-data|flex [--any-time]
#                                                  preflight (role, password, db-step progress, manifests that read
#                                                  postgres-user), then one Secret patch and a restart
#   plugin-db-roles.sh rollback market-data|flex   the same keys back to bifrost (password from the CNPG
#                                                  Secret); restart
#   plugin-db-roles.sh check [market-data|flex]    yes / no answers, and sessions per user from the plugin's pods
#
# Order and SQL: scripts/release/db-steps.d/2026-10-04-d6-plugins-off-bifrost.md (steps 1-3 before switch,
# step 4 after both). switch refuses during the market-data batch window (weekdays 20:55-23:30 UTC) unless
# --any-time is given.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${BIFROST_TRADE_INFRA_ENV:-$ROOT/.env}"
export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}"
CNPG_NS=data
CNPG_SECRET=bifrost-postgres-app

plugin_help() { sed -n '2,27p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }
stop_here() { echo "ERROR: $*" >&2; exit 1; }

TMPS=()
trap 'rm -f "${TMPS[@]:-}"' EXIT
tmp_private() {  # tmp_private VAR: a mode-600 temp file, removed on exit
  local f
  f="$(mktemp)"
  chmod 600 "$f"
  TMPS+=("$f")
  printf -v "$1" '%s' "$f"
}

# Everything per plugin, in one place. plugin_vars <plugin> sets: NS SECRET ROLE ENVKEY PW_KEYS DEPLOYS
# USER_ENVS (env names that must read postgres-user in every workload) TRADE_DB (flex: the Trade
# database it reads, from the Secret; market-data: none).
plugin_vars() {
  case "${1:-}" in
    market-data)
      NS=plugin-market-data; SECRET=market-data-secrets; ROLE=data_writer; ENVKEY=DATA_WRITER_PG_PASSWORD
      PW_KEYS=postgres-password; DEPLOYS=(market-data-api polygon-worker-stocks polygon-worker-options)
      USER_ENVS=(POSTGRES_USER); TRADE_DB="" ;;
    flex)
      NS=plugin-flex-query; SECRET=flex-query-secrets; ROLE=flex_writer; ENVKEY=FLEX_WRITER_PG_PASSWORD
      PW_KEYS=postgres-password,trade-pg-password; DEPLOYS=(flex-query-api flex-query-worker)
      USER_ENVS=(POSTGRES_USER GOLDEN_SOURCE_USER FLEX_TRADE_PG_USER)
      TRADE_DB="$(secret_value plugin-flex-query flex-query-secrets trade-pg-db 2>/dev/null || echo bifrost_dev)" ;;
    *) stop_here "unknown plugin: '${1:-}' (market-data or flex)" ;;
  esac
}
role_envkey() {
  case "${1:-}" in
    data_writer) echo DATA_WRITER_PG_PASSWORD ;;
    flex_writer) echo FLEX_WRITER_PG_PASSWORD ;;
    *) stop_here "unknown role: '${1:-}' (data_writer or flex_writer)" ;;
  esac
}

primary_pod() {
  local p
  p="$(kubectl -n data get cluster bifrost-postgres -o jsonpath='{.status.currentPrimary}' 2>/dev/null || true)"
  echo "${p:-bifrost-postgres-1}"
}
# PLUGIN_DB_ROLES_DB_EXEC replaces the kubectl exec prefix (rehearsal against a local container only).
in_db() {
  if [[ -n "${PLUGIN_DB_ROLES_DB_EXEC:-}" ]]; then
    local pre
    read -r -a pre <<<"$PLUGIN_DB_ROLES_DB_EXEC"
    "${pre[@]}" "$@"
  else
    kubectl -n data exec -i "$(primary_pod)" -c postgres -- "$@"
  fi
}
q_ro() {  # q_ro DB SQL: read-only, tuples only
  in_db psql -U postgres -d "$1" -X -tA -c "SET default_transaction_read_only=on;" -c "$2" | { grep -v '^SET$' || true; }
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
    sys.exit(f"{key} is not set in {path}; run: scripts/plugin-db-roles.sh ensure")
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

# signs_in USER DB: password on stdin, TCP login inside the database pod.
signs_in() {
  in_db sh -c 'IFS= read -r PGPASSWORD || true; export PGPASSWORD
    psql -h localhost -U "$0" -d "$1" -X -tAc "SELECT 1" >/dev/null 2>&1' "$1" "$2"
}
yes_no() { if "$@"; then echo yes; else echo no; fi; }

role_state() {  # role_state ROLE -> missing | present, password set | present, NO password
  q_ro postgres "SELECT CASE WHEN a.oid IS NULL THEN 'missing'
                             WHEN a.rolpassword LIKE 'SCRAM-SHA-256\$%' THEN 'present, password set'
                             ELSE 'present, NO password' END
                   FROM (SELECT 1) one LEFT JOIN pg_authid a ON a.rolname = '$1';"
}

# db_ready PLUGIN: the db-step's steps 1-3 are in (yes / the first thing missing).
db_ready() {
  local out
  if [[ "$1" == market-data ]]; then
    out="$(q_ro bifrost_golden_source "SELECT CASE
        WHEN pg_get_userbyid((SELECT nspowner FROM pg_namespace WHERE nspname = 'raw_market')) <> 'data_writer' THEN 'step 3: raw_market is not owned by data_writer'
        WHEN pg_get_userbyid((SELECT relowner FROM pg_class WHERE oid = 'ops_jobs.job_ingest'::regclass)) <> 'data_writer' THEN 'step 3: ops_jobs.job_ingest is not owned by data_writer'
        WHEN NOT has_table_privilege('data_writer', 'research.option_universe', 'SELECT') OR NOT has_schema_privilege('data_writer', 'research', 'USAGE') THEN 'step 2: data_writer cannot read research.option_universe'
        WHEN NOT coalesce((SELECT 'statement_timeout=2s' = ANY (setconfig) FROM pg_db_role_setting WHERE setrole = 'data_writer'::regrole AND setdatabase = 0), false) THEN 'step 1: data_writer has no role settings'
        ELSE 'yes' END;")"
  else
    out="$(q_ro bifrost_golden_source "SELECT CASE
        WHEN to_regrole('flex_writer') IS NULL THEN 'step 1: role flex_writer is missing'
        WHEN pg_get_userbyid((SELECT relowner FROM pg_class WHERE oid = 'ops_jobs.job_flex_ingest'::regclass)) <> 'flex_writer' THEN 'step 3: ops_jobs.job_flex_ingest is not owned by flex_writer'
        WHEN NOT has_table_privilege('flex_writer', 'raw_broker.executions_raw_flex', 'INSERT, UPDATE') THEN 'step 2: flex_writer cannot write raw_broker.executions_raw_flex'
        ELSE 'yes' END;")"
    if [[ "$out" == yes ]]; then
      out="$(q_ro "$TRADE_DB" "SELECT CASE
          WHEN NOT has_table_privilege('flex_writer', 'brokerage.settings_flex', 'SELECT') THEN 'step 2: flex_writer cannot read brokerage.settings_flex in $TRADE_DB'
          WHEN NOT EXISTS (SELECT 1 FROM pg_user_mappings WHERE srvname = 'golden_source_server' AND usename = 'flex_writer') THEN 'step 2: no user mapping for flex_writer in $TRADE_DB'
          ELSE 'yes' END;")"
    fi
  fi
  echo "$out"
}

# manifests_ready: every Deployment / CronJob in the namespace that maps a password key of the plugin's
# Secret also maps each USER_ENVS name to its postgres-user key (the plugin release is applied).
manifests_ready() {
  kubectl -n "$NS" get deploy,cronjob -o json | python3 -c '
import json, sys
secret, pw_keys, user_envs = sys.argv[1], set(sys.argv[2].split(",")), sys.argv[3].split(",")
bad = []
for d in json.load(sys.stdin)["items"]:
    spec = d["spec"]
    t = spec.get("jobTemplate", {}).get("spec", {}).get("template") or spec["template"]
    for c in t["spec"]["containers"]:
        refs = {e["name"]: ((e.get("valueFrom") or {}).get("secretKeyRef") or {}) for e in c.get("env") or []}
        if not any(r.get("name") == secret and r.get("key") in pw_keys for r in refs.values()):
            continue
        for n in user_envs:
            r = refs.get(n) or {}
            if r.get("name") != secret or r.get("key") != "postgres-user":
                kind, wname = d["kind"], d["metadata"]["name"]
                bad.append(f"{kind}/{wname}:{n}")
if bad:
    print("missing postgres-user for " + ", ".join(bad))
    sys.exit(1)
' "$SECRET" "$PW_KEYS" "$(IFS=,; echo "${USER_ENVS[*]}")"
}

batch_window() {  # 0 inside the market-data batch window
  python3 - <<'PY'
import datetime, sys
now = datetime.datetime.now(datetime.timezone.utc)
mins = now.hour * 60 + now.minute
sys.exit(0 if now.weekday() < 5 and 20 * 60 + 55 <= mins < 23 * 60 + 30 else 1)
PY
}

# set_login USER: password on stdin -> one merge patch of postgres-user + every password key.
set_login() {
  local patch
  tmp_private patch
  python3 -c '
import json, sys
user, keys, out = sys.argv[1], sys.argv[2].split(","), sys.argv[3]
pw = sys.stdin.read()
if not pw:
    sys.exit("no password on stdin; nothing changed")
data = {"postgres-user": user}
data.update({k: pw for k in keys})
json.dump({"stringData": data}, open(out, "w"))
' "$1" "$PW_KEYS" "$patch"
  kubectl -n "$NS" patch secret "$SECRET" --type merge --patch-file "$patch" >/dev/null
  echo "$NS/$SECRET: postgres-user -> $1, ${PW_KEYS} updated (values omitted)"
}

restart_plugin() {
  local d
  for d in "${DEPLOYS[@]}"; do
    kubectl -n "$NS" rollout restart "deploy/$d" >/dev/null
  done
  for d in "${DEPLOYS[@]}"; do
    kubectl -n "$NS" rollout status "deploy/$d" --timeout=600s >/dev/null
  done
  echo "restarted in $NS: ${DEPLOYS[*]} (CronJobs and the migrate Job take the Secret on their next run)"
}

sessions() {  # sessions by user for the plugin namespace's running pods
  local ips
  tmp_private ips
  kubectl -n "$NS" get pods --field-selector=status.phase=Running \
    -o jsonpath='{range .items[*]}{.status.podIP} {.metadata.name}{"\n"}{end}' >"$ips"
  q_ro postgres "SELECT host(client_addr), usename, datname FROM pg_stat_activity WHERE client_addr IS NOT NULL;" |
    python3 -c '
import collections, sys
pods = dict(l.split() for l in open(sys.argv[1]) if len(l.split()) == 2)
agg = collections.Counter()
for line in sys.stdin:
    p = line.strip().split("|")
    if len(p) == 3 and p[0] in pods:
        agg[(p[1], p[2])] += 1
if not agg:
    print("  (no sessions from this namespace right now)")
for (u, db), n in sorted(agg.items()):
    print(f"  {u:<14} {db:<24} {n}")
' "$ips"
}

show_check() {
  local p="$1" k
  plugin_vars "$p"
  echo "== $p ($NS) -> $ROLE"
  echo "role $ROLE: $(role_state "$ROLE")"
  if env_value "$ENVKEY" >/dev/null 2>&1; then
    echo "local $ENVKEY signs in as $ROLE to bifrost_golden_source: $(env_value "$ENVKEY" | yes_no signs_in "$ROLE" bifrost_golden_source)"
    [[ -z "$TRADE_DB" ]] || echo "local $ENVKEY signs in as $ROLE to $TRADE_DB: $(env_value "$ENVKEY" | yes_no signs_in "$ROLE" "$TRADE_DB")"
  else
    echo "local $ENVKEY: not set"
  fi
  echo "db-step steps 1-3 in place: $(db_ready "$p")"
  echo "manifests read postgres-user: $(manifests_ready && echo yes || true)"
  echo "$NS/$SECRET postgres-user: $(secret_value "$NS" "$SECRET" postgres-user 2>/dev/null || echo '(unset: ConfigMap user, bifrost)')"
  for k in ${PW_KEYS//,/ }; do
    state=$( { env_value "$ENVKEY" 2>/dev/null || true; printf '\0'; secret_value "$CNPG_NS" "$CNPG_SECRET" password 2>/dev/null || true; printf '\0'; secret_value "$NS" "$SECRET" "$k" 2>/dev/null || true; } |
      python3 -c '
import sys
mine, bif, live = (sys.stdin.buffer.read().split(b"\0") + [b"", b"", b""])[:3]
print("missing" if not live else f"{sys.argv[1]} value: " + ("yes" if mine and live == mine else "no") + ", bifrost value: " + ("yes" if bif and live == bif else "no"))
' "$ROLE")
    echo "$NS/$SECRET $k: $state"
  done
  echo "sessions from $NS pods (user, database, count):"
  sessions
}

cmd="${1:-}"
[[ -n "$cmd" ]] || plugin_help
shift

case "$cmd" in
ensure)
  [[ -f "$ENV_FILE" ]] || (umask 077 && : >"$ENV_FILE")
  python3 - "$ENV_FILE" <<'PY'
import re, secrets, sys
path = sys.argv[1]
text = open(path, encoding="utf-8").read()
added = []
for key in ("DATA_WRITER_PG_PASSWORD", "FLEX_WRITER_PG_PASSWORD"):
    m = re.search(rf"^{key}=(.*)$", text, flags=re.M)
    if m and m.group(1).strip().strip('"').strip("'"):
        continue
    line = f"{key}={secrets.token_urlsafe(32)}"
    if m:
        text = re.sub(rf"^{key}=.*$", lambda _m: line, text, count=1, flags=re.M)
    else:
        text = text + ("" if not text or text.endswith("\n") else "\n") + line + "\n"
    added.append(key)
open(path, "w", encoding="utf-8").write(text)
print(("generated " + ", ".join(added) if added else "both are set; nothing to do") + f" ({path}, values omitted)")
PY
  ;;

password)
  role="${1:-}"
  key="$(role_envkey "$role")"
  [[ "$(role_state "$role")" != missing ]] || stop_here "$role does not exist: run step 1 of the db-step first"
  env_value "$key" >/dev/null
  # SCRAM-SHA-256 verifier (RFC 5802 / 7677, what psql's \password sends). token_urlsafe values are ASCII,
  # so SASLprep is the identity.
  env_value "$key" | python3 -c '
import base64, hashlib, hmac, os, sys
role = sys.argv[1]
pw = sys.stdin.read().encode()
salt, it = os.urandom(16), 4096
salted = hashlib.pbkdf2_hmac("sha256", pw, salt, it)
ck = hmac.new(salted, b"Client Key", "sha256").digest()
sk = hmac.new(salted, b"Server Key", "sha256").digest()
b = lambda x: base64.b64encode(x).decode()
print("\\set ON_ERROR_STOP on")
print(f"ALTER ROLE {role} PASSWORD $v$SCRAM-SHA-256${it}:{b(salt)}${b(hashlib.sha256(ck).digest())}:{b(sk)}$v$;")
' "$role" | in_db psql -U postgres -d postgres -X -q
  echo "$role: password set (verifier only); signs in to bifrost_golden_source: $(env_value "$key" | yes_no signs_in "$role" bifrost_golden_source)"
  ;;

switch)
  p="${1:-}"
  plugin_vars "$p"
  if [[ "${2:-}" != --any-time ]] && batch_window; then
    stop_here "inside the market-data batch window (weekdays 20:55-23:30 UTC); pass --any-time to override"
  fi
  [[ "$(role_state "$ROLE")" == "present, password set" ]] || stop_here "$ROLE: $(role_state "$ROLE"); run: $0 password $ROLE"
  env_value "$ENVKEY" >/dev/null
  env_value "$ENVKEY" | signs_in "$ROLE" bifrost_golden_source || stop_here "the local $ENVKEY does not sign in as $ROLE to bifrost_golden_source"
  if [[ -n "$TRADE_DB" ]]; then
    env_value "$ENVKEY" | signs_in "$ROLE" "$TRADE_DB" || stop_here "the local $ENVKEY does not sign in as $ROLE to $TRADE_DB"
  fi
  ready="$(db_ready "$p")"
  [[ "$ready" == yes ]] || stop_here "db-step not ready: $ready"
  manifests_ready || stop_here "apply the plugin release that reads postgres-user first (market-data >= 0.76.0, flex-query >= 0.9.0)"
  secret_value "$CNPG_NS" "$CNPG_SECRET" password >/dev/null || stop_here "cannot read $CNPG_NS/$CNPG_SECRET (a rollback needs it); nothing changed"
  if [[ "$p" == market-data ]] && [[ "$(kubectl -n "$NS" get job job-wave8-schema-migrate -o jsonpath='{.status.active}' 2>/dev/null || true)" != "" ]]; then
    stop_here "the migrate Job is running in $NS; wait for it"
  fi
  env_value "$ENVKEY" | set_login "$ROLE"
  restart_plugin
  echo "done. Now: $0 check $p  (then the verify list in the db-step file; step 4 after both plugins)"
  ;;

rollback)
  p="${1:-}"
  plugin_vars "$p"
  secret_value "$CNPG_NS" "$CNPG_SECRET" password | signs_in bifrost bifrost_golden_source ||
    stop_here "the CNPG Secret's value does not sign in as bifrost; nothing changed"
  secret_value "$CNPG_NS" "$CNPG_SECRET" password | set_login bifrost
  restart_plugin
  echo "done. bifrost needs the db-step's bridge grants or its rollback files to work in raw_market / ops_jobs: $0 check $p"
  ;;

check)
  if [[ $# -eq 0 ]]; then set -- market-data flex; fi
  for p in "$@"; do show_check "$p"; done
  ;;

*)
  plugin_help
  ;;
esac
