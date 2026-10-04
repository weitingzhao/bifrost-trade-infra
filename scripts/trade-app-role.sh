#!/usr/bin/env bash
# Owner-run: the Trade runtime signs in to Postgres as its own role, trade_app_<env> (TD-85 D1),
# instead of bifrost; bifrost stays with db-init (DDL) through Secret bifrost-<env>-db-owner.
#
# Passwords live in this repo's gitignored .env (TRADE_APP_{DEV,STG,PROD}_PG_PASSWORD) and in the
# Secrets. No subcommand prints one; they travel on stdin or in mode-600 temp files removed on exit,
# never on a command line (not in shell history, not in `ps`).
#
#   trade-app-role.sh ensure                  generate the missing TRADE_APP_*_PG_PASSWORD into .env
#   trade-app-role.sh password <env>...       set trade_app_<env>'s password: a SCRAM-SHA-256 verifier
#                                             is computed here and sent; the password never reaches
#                                             Postgres or its logs
#   trade-app-role.sh owner-secret <env>...   create bifrost-<env>-db-owner (db-init's login: PGUSER /
#                                             GOLDEN_SOURCE_USER = bifrost + the two passwords) from what
#                                             bifrost-<env>-secrets carries while it is still on bifrost
#   trade-app-role.sh switch <env>            bifrost-<env>-secrets -> trade_app_<env> (PGUSER,
#                                             GOLDEN_SOURCE_USER, PGPASSWORD, GOLDEN_SOURCE_PASSWORD in one
#                                             patch), then restart the env's Trade Deployments
#   trade-app-role.sh rollback <env>          the same four keys back to bifrost, values taken from
#                                             bifrost-<env>-db-owner; restart
#   trade-app-role.sh check <env>             yes / no answers, and sessions per user
#
# <env> is dev, stg or prod. The role and its grants come from
# scripts/release/db-steps.d/2026-10-04-td85-trade-app-roles.md (the Owner runs that SQL first).
# switch prod refuses during US regular trading hours unless --during-market-hours is given.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${BIFROST_TRADE_INFRA_ENV:-$ROOT/.env}"
export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}"
# Trade Deployments that take PG* / GOLDEN_SOURCE_* from bifrost-<env>-secrets (envFrom). The
# db-init Job is not here: it reads bifrost-<env>-db-owner and runs with the next deliver.
TRADE_DEPLOYS=(api-account api-market api-monitor api-research daemon)

show_help() { sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }
abort() { echo "ERROR: $*" >&2; exit 1; }

check_env_name() { case "${1:-}" in dev | stg | prod) ;; *) abort "unknown env: '${1:-}' (dev, stg or prod)" ;; esac; }
upper() { tr '[:lower:]' '[:upper:]' <<<"$1"; }
key_for() { echo "TRADE_APP_$(upper "$1")_PG_PASSWORD"; }

TMPFILES=()
trap 'rm -f "${TMPFILES[@]:-}"' EXIT
mktemp_private() {  # mktemp_private VAR: a mode-600 temp file, removed on exit
  local f
  f="$(mktemp)"
  chmod 600 "$f"
  TMPFILES+=("$f")
  printf -v "$1" '%s' "$f"
}

# psql in the CNPG primary (it moves on a switchover; bifrost-postgres-1 is only the default).
pg_pod() {
  local p
  p="$(kubectl -n data get cluster bifrost-postgres -o jsonpath='{.status.currentPrimary}' 2>/dev/null || true)"
  echo "${p:-bifrost-postgres-1}"
}
pg() { kubectl -n data exec -i "$(pg_pod)" -c postgres -- "$@"; }

# Prints the local value on stdout, for a pipe only. Exits 1 when it is absent.
local_value() {
  python3 - "$ENV_FILE" "$1" <<'PY'
import re, sys
path, key = sys.argv[1], sys.argv[2]
try:
    text = open(path, encoding="utf-8").read()
except FileNotFoundError:
    text = ""
m = re.search(rf"^{key}=(.*)$", text, flags=re.M)
val = (m.group(1).strip().strip('"').strip("'") if m else "")
if not val:
    sys.exit(f"{key} is not set in {path}; run: scripts/trade-app-role.sh ensure")
sys.stdout.write(val)
PY
}

# Reads a password on stdin and tries it as <user> on <db> over TCP inside the database pod.
signs_in() {
  pg sh -c 'IFS= read -r PGPASSWORD || true; export PGPASSWORD
    psql -h localhost -U "$0" -d "$1" -X -tAc "SELECT 1" >/dev/null 2>&1' "$1" "$2"
}
yes_no() { if "$@"; then echo yes; else echo no; fi; }

role_state() {  # role_state <role> -> missing | present, password set | present, NO password
  pg psql -U postgres -d postgres -X -tA -c "SET default_transaction_read_only=on;" -c "
    SELECT CASE WHEN a.oid IS NULL THEN 'missing'
                WHEN a.rolpassword LIKE 'SCRAM-SHA-256\$%' THEN 'present, password set'
                ELSE 'present, NO password' END
      FROM (SELECT 1) one LEFT JOIN pg_authid a ON a.rolname = '$1';" | grep -v '^SET$'
}

secret_json() {  # secret_json <ns> <name> -> the Secret as JSON, or nothing
  kubectl -n "$1" get secret "$2" -o json 2>/dev/null || true
}

# One field of a Secret, decoded, on stdout (for a pipe only); exits 1 when absent.
secret_field() {
  secret_json "$1" "$2" | python3 -c '
import base64, json, sys
raw = sys.stdin.read()
if not raw.strip():
    sys.exit(1)
v = (json.loads(raw).get("data") or {}).get(sys.argv[1])
if not v:
    sys.exit(1)
sys.stdout.write(base64.b64decode(v).decode())
' "$3"
}

# Patch the four connection keys of bifrost-<env>-secrets (live, and the gitignored local copy
# it is materialized from). $2 = user; the password comes on stdin.
read -r -d '' SET_LOGIN_PY <<'PY' || true
import json, os, re, sys
user, local_file, patch = sys.argv[1], sys.argv[2], sys.argv[3]
pw = sys.stdin.read()
if not pw:
    sys.exit("no password on stdin; nothing changed")
vals = {"PGUSER": user, "GOLDEN_SOURCE_USER": user, "PGPASSWORD": pw, "GOLDEN_SOURCE_PASSWORD": pw}
with open(patch, "w", encoding="utf-8") as f:
    json.dump({"stringData": vals}, f)
if os.path.isfile(local_file):
    text = open(local_file, encoding="utf-8").read()
    for k, v in vals.items():
        esc = v.replace("\\", "\\\\").replace('"', '\\"')
        pat = rf"(^[ \t]*{re.escape(k)}:[ \t]*).*$"
        if re.search(pat, text, flags=re.M):
            text = re.sub(pat, lambda m: f'{m.group(1)}"{esc}"', text, count=1, flags=re.M)
        else:
            text = re.sub(r"(^stringData:\n)", lambda m: f'{m.group(1)}  {k}: "{esc}"\n', text, count=1, flags=re.M)
    open(local_file, "w", encoding="utf-8").write(text)
    os.chmod(local_file, 0o600)
    print(f"updated {local_file} -> {user} (values omitted)", file=sys.stderr)
PY
set_runtime_login() {
  local env="$1" user="$2" ns="bifrost-$1" patch
  mktemp_private patch
  python3 -c "$SET_LOGIN_PY" "$user" "$ROOT/k8s/base/secrets/bifrost-$env-secrets.yaml" "$patch"
  kubectl -n "$ns" patch secret "bifrost-$env-secrets" --type merge --patch-file "$patch" >/dev/null
  echo "$ns/bifrost-$env-secrets: PGUSER / GOLDEN_SOURCE_USER -> $user (passwords omitted)"
}

restart_trade() {
  local ns="$1" d
  for d in "${TRADE_DEPLOYS[@]}"; do
    kubectl -n "$ns" get deploy "$d" >/dev/null 2>&1 || continue
    kubectl -n "$ns" rollout restart "deploy/$d" >/dev/null
  done
  for d in "${TRADE_DEPLOYS[@]}"; do
    kubectl -n "$ns" get deploy "$d" >/dev/null 2>&1 || continue
    kubectl -n "$ns" rollout status "deploy/$d" --timeout=300s >/dev/null
  done
  echo "restarted in $ns: ${TRADE_DEPLOYS[*]} (those that exist)"
}

owner_secret_ok() {  # owner_secret_ok <env>: the four keys are there and its password signs in as bifrost
  local env="$1" ns="bifrost-$1" k
  for k in PGUSER GOLDEN_SOURCE_USER PGPASSWORD GOLDEN_SOURCE_PASSWORD; do
    secret_field "$ns" "bifrost-$env-db-owner" "$k" >/dev/null || return 1
  done
  [[ "$(secret_field "$ns" "bifrost-$env-db-owner" PGUSER)" == bifrost ]] || return 1
  secret_field "$ns" "bifrost-$env-db-owner" PGPASSWORD | signs_in bifrost "bifrost_$env"
}

us_market_open() {  # NYSE regular session, Mon-Fri 09:30-16:00 America/New_York (holidays not modelled)
  python3 - <<'PY'
import datetime, sys
from zoneinfo import ZoneInfo
now = datetime.datetime.now(ZoneInfo("America/New_York"))
open_ = now.weekday() < 5 and (9, 30) <= (now.hour, now.minute) < (16, 0)
sys.exit(0 if open_ else 1)
PY
}

# Builds Secret bifrost-<env>-db-owner from bifrost-<env>-secrets (JSON on stdin) and writes the
# gitignored local copy; prints the Secret as JSON for kubectl apply.
read -r -d '' OWNER_SECRET_PY <<'PY' || true
import base64, json, os, sys
env, local_file = sys.argv[1], sys.argv[2]
d = json.load(sys.stdin).get("data") or {}
pw = d["PGPASSWORD"]
gs = d.get("GOLDEN_SOURCE_PASSWORD") or pw
b = lambda s: base64.b64encode(s.encode()).decode()
name, ns = f"bifrost-{env}-db-owner", f"bifrost-{env}"
data = {"PGUSER": b("bifrost"), "GOLDEN_SOURCE_USER": b("bifrost"), "PGPASSWORD": pw, "GOLDEN_SOURCE_PASSWORD": gs}
labels = {"app.kubernetes.io/part-of": "bifrost", "app.kubernetes.io/component": "db-init"}
lines = ["apiVersion: v1", "kind: Secret", "metadata:", f"  name: {name}", "  labels:"]
lines += [f"    {k}: {v}" for k, v in labels.items()]
lines += ["type: Opaque", "stringData:"]
for k, v in data.items():
    val = base64.b64decode(v).decode().replace("\\", "\\\\").replace('"', '\\"')
    lines.append(f'  {k}: "{val}"')
os.makedirs(os.path.dirname(local_file), exist_ok=True)
with open(local_file, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
os.chmod(local_file, 0o600)
meta = {"name": name, "namespace": ns, "labels": labels}
json.dump({"apiVersion": "v1", "kind": "Secret", "type": "Opaque", "metadata": meta, "data": data}, sys.stdout)
PY

cmd="${1:-}"
[[ -n "$cmd" ]] || show_help
shift

case "$cmd" in
ensure)
  [[ -f "$ENV_FILE" ]] || (umask 077 && : >"$ENV_FILE")
  python3 - "$ENV_FILE" <<'PY'
import re, secrets, sys
path = sys.argv[1]
text = open(path, encoding="utf-8").read()
added = []
for env in ("DEV", "STG", "PROD"):
    key = f"TRADE_APP_{env}_PG_PASSWORD"
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
print(("generated " + ", ".join(added) if added else "all three are set; nothing to do") + f" ({path}, values omitted)")
PY
  ;;

password)
  [[ $# -gt 0 ]] || show_help
  for env in "$@"; do check_env_name "$env"; done
  for env in "$@"; do
    role="trade_app_$env"
    state="$(role_state "$role")"
    [[ "$state" != missing ]] || abort "$role does not exist: run the db-step 2026-10-04-td85-trade-app-roles first"
    local_value "$(key_for "$env")" >/dev/null
    # SCRAM-SHA-256 verifier (RFC 5802 / 7677, what psql's \password sends). token_urlsafe values
    # are ASCII, so SASLprep is the identity.
    local_value "$(key_for "$env")" | python3 -c '
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
' "$role" | pg psql -U postgres -d postgres -X -q
    echo "$role: password set (verifier only); signs in to bifrost_$env: $(local_value "$(key_for "$env")" | yes_no signs_in "$role" "bifrost_$env")"
  done
  ;;

owner-secret)
  [[ $# -gt 0 ]] || show_help
  for env in "$@"; do check_env_name "$env"; done
  for env in "$@"; do
    ns="bifrost-$env"
    if [[ -n "$(secret_json "$ns" "bifrost-$env-db-owner")" ]]; then
      echo "$ns/bifrost-$env-db-owner exists; left as is. Signs in as bifrost: $(yes_no owner_secret_ok "$env")"
      continue
    fi
    src="$(secret_json "$ns" "bifrost-$env-secrets" | python3 -c '
import base64, json, sys
raw = sys.stdin.read()
d = (json.loads(raw).get("data") or {}) if raw.strip() else {}
user = base64.b64decode(d.get("PGUSER", "")).decode() or "bifrost"
print("ok" if d.get("PGPASSWORD") and user == "bifrost" else "refuse:" + ("no PGPASSWORD" if not d.get("PGPASSWORD") else "PGUSER is " + user))
')"
    [[ "$src" == ok ]] || abort "$ns/bifrost-$env-secrets cannot seed the owner Secret (${src#refuse:}); create bifrost-$env-db-owner by hand from the bifrost password"
    # Built from the live Secret in one pipe: the values go from kubectl to kubectl, and into the
    # gitignored local copy, never to the terminal.
    secret_json "$ns" "bifrost-$env-secrets" | python3 -c "$OWNER_SECRET_PY" "$env" "$ROOT/k8s/base/secrets/bifrost-$env-db-owner.yaml" |
      kubectl apply --server-side --field-manager=trade-app-role -f - >/dev/null
    echo "$ns/bifrost-$env-db-owner created (values omitted; local copy k8s/base/secrets/bifrost-$env-db-owner.yaml)." \
      "Signs in as bifrost: $(yes_no owner_secret_ok "$env")"
  done
  ;;

switch)
  env="${1:-}"
  check_env_name "$env"
  ns="bifrost-$env"
  role="trade_app_$env"
  if [[ "$env" == prod && "${2:-}" != --during-market-hours ]] && us_market_open; then
    abort "US regular session is open; switch PROD after the close (or pass --during-market-hours)"
  fi
  [[ "$(role_state "$role")" == "present, password set" ]] || abort "$role: $(role_state "$role"); run the db-step, then: $0 password $env"
  local_value "$(key_for "$env")" >/dev/null
  local_value "$(key_for "$env")" | signs_in "$role" "bifrost_$env" || abort "the local $(key_for "$env") does not sign in as $role to bifrost_$env"
  local_value "$(key_for "$env")" | signs_in "$role" bifrost_golden_source || abort "the local $(key_for "$env") does not sign in as $role to bifrost_golden_source"
  owner_secret_ok "$env" || abort "$ns/bifrost-$env-db-owner is missing, incomplete or does not sign in as bifrost: $0 owner-secret $env (rollback needs it)"
  # db-init must keep signing in as bifrost: the manifest in this checkout has the override, and a
  # db-init Job still running from the old template would sign in as trade_app_<env> and fail.
  case "$env" in
    dev) job_manifest="$ROOT/k8s/overlays/dev/db-init-dev.job.yaml" ;;
    stg) job_manifest="$ROOT/k8s/base/jobs/db-init.yaml" ;;
    prod) job_manifest="$ROOT/k8s/overlays/prod/db-init-prod.job.yaml" ;;
  esac
  grep -q "bifrost-$env-db-owner" "$job_manifest" ||
    abort "$job_manifest has no bifrost-$env-db-owner override: merge the TD-85 infra change first"
  if kubectl -n "$ns" get job "db-init-$env" >/dev/null 2>&1; then
    job_state="$(kubectl -n "$ns" get job "db-init-$env" -o json | python3 -c '
import json, sys
j = json.load(sys.stdin)
has = sys.argv[1] in json.dumps(j.get("spec", {}))
active = (j.get("status") or {}).get("active", 0)
print("ok" if has else ("running-old" if active else "finished-old"))
' "bifrost-$env-db-owner")"
    [[ "$job_state" != running-old ]] ||
      abort "a db-init-$env Job from the old template is running in $ns; wait for it to finish"
    [[ "$job_state" != finished-old ]] ||
      echo "note: the finished db-init-$env Job in $ns is from the old template; the next one (after its TTL) comes from git with the override"
  fi
  local_value "$(key_for "$env")" | set_runtime_login "$env" "$role"
  restart_trade "$ns"
  echo "done. Now: $0 check $env  (and the verify list in the db-step file)"
  ;;

rollback)
  env="${1:-}"
  check_env_name "$env"
  ns="bifrost-$env"
  owner_secret_ok "$env" || abort "$ns/bifrost-$env-db-owner is missing or does not sign in as bifrost; nothing changed"
  secret_field "$ns" "bifrost-$env-db-owner" PGPASSWORD | set_runtime_login "$env" bifrost
  restart_trade "$ns"
  echo "done. Now: $0 check $env"
  ;;

check)
  env="${1:-}"
  check_env_name "$env"
  ns="bifrost-$env"
  role="trade_app_$env"
  key="$(key_for "$env")"
  echo "role $role: $(role_state "$role")"
  if local_value "$key" >/dev/null 2>&1; then
    echo "local $key: set"
    echo "local $key signs in as $role to bifrost_$env: $(local_value "$key" | yes_no signs_in "$role" "bifrost_$env")"
    echo "local $key signs in as $role to bifrost_golden_source: $(local_value "$key" | yes_no signs_in "$role" bifrost_golden_source)"
  else
    echo "local $key: not set"
  fi
  echo "$ns/bifrost-$env-db-owner complete and signs in as bifrost: $(yes_no owner_secret_ok "$env")"
  echo "$ns/bifrost-$env-secrets PGUSER: $(secret_field "$ns" "bifrost-$env-secrets" PGUSER 2>/dev/null || echo '(unset: config user, bifrost)')"
  echo "$ns/bifrost-$env-secrets GOLDEN_SOURCE_USER: $(secret_field "$ns" "bifrost-$env-secrets" GOLDEN_SOURCE_USER 2>/dev/null || echo '(unset: config user, bifrost)')"
  # Equality is decided in python; neither value is printed.
  for k in PGPASSWORD GOLDEN_SOURCE_PASSWORD; do
    state=$( { local_value "$key" 2>/dev/null || true; printf '\n'; secret_field "$ns" "bifrost-$env-secrets" "$k" 2>/dev/null || true; printf '\n'; secret_field "$ns" "bifrost-$env-db-owner" PGPASSWORD 2>/dev/null || true; } |
      python3 -c '
import sys
local, live, owner = (sys.stdin.read().split("\n") + ["", "", ""])[:3]
if not live:
    print("missing")
else:
    print("trade_app value: " + ("yes" if local and live == local else "no") + ", bifrost value: " + ("yes" if owner and live == owner else "no"))
')
    echo "$ns/bifrost-$env-secrets $k: $state"
  done
  echo "sessions on bifrost_$env and bifrost_golden_source by user (GS bifrost includes the plugins):"
  pg psql -U postgres -d postgres -X -tA -F' ' -c "SET default_transaction_read_only=on;" -c "
    SELECT datname, usename, count(*) FROM pg_stat_activity
     WHERE datname IN ('bifrost_$env', 'bifrost_golden_source') AND usename IN ('bifrost', '$role')
     GROUP BY 1, 2 ORDER BY 1, 2;" | { grep -v '^SET$' || echo "(none)"; } | sed 's/^/  /'
  ;;

*)
  show_help
  ;;
esac
