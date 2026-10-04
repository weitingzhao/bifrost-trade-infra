#!/usr/bin/env bash
# Owner-run: the password of Golden Source role feedback_writer and the Secret that carries it to
# trade-api's feedback store (TD-49 D4 / TD-77 E5; api 0.7.5 reads FEEDBACK_PG_*).
#
# One local value, FEEDBACK_PG_PASSWORD in this repo's gitignored .env, feeds both the role and the
# Secret bifrost-feedback-secrets in each Trade namespace. No subcommand prints it, and it never
# appears on a command line (it travels on stdin): not in shell history, not in `ps`.
#
#   feedback-writer-secret.sh ensure              generate FEEDBACK_PG_PASSWORD into .env if it is absent
#   feedback-writer-secret.sh password            set the role's password: a SCRAM-SHA-256 verifier is
#                                                 computed here and sent; the password never reaches
#                                                 Postgres or its logs
#   feedback-writer-secret.sh secret <env>...     create or update bifrost-feedback-secrets in
#                                                 bifrost-<env> (dev, stg, prod); restarts nothing
#   feedback-writer-secret.sh check [<env>...]    role set? local value signs in? Secret present and
#                                                 equal to the local value? (yes / no only)
#
# The role itself comes from scripts/release/db-steps.d/2026-10-04-td49-feedback-writer-role.md.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${BIFROST_TRADE_INFRA_ENV:-$ROOT/.env}"
export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}"
PG=(kubectl -n data exec -i bifrost-postgres-1 -c postgres --)
SECRET=bifrost-feedback-secrets
KEY=FEEDBACK_PG_PASSWORD

feedback_usage() { sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }

# Prints the local value on stdout, for a pipe only. Exits 1 when it is absent.
local_value() {
  python3 - "$ENV_FILE" "$KEY" <<'PY'
import re, sys
path, key = sys.argv[1], sys.argv[2]
try:
    text = open(path, encoding="utf-8").read()
except FileNotFoundError:
    text = ""
m = re.search(rf"^{key}=(.*)$", text, flags=re.M)
val = (m.group(1).strip().strip('"').strip("'") if m else "")
if not val:
    sys.exit(f"{key} is not set in {path}; run: scripts/feedback-writer-secret.sh ensure")
sys.stdout.write(val)
PY
}

envs_or_all() { if [[ $# -gt 0 ]]; then echo "$@"; else echo dev stg prod; fi; }

check_env_name() { case "$1" in dev | stg | prod) ;; *) echo "unknown env: $1" >&2; exit 2 ;; esac; }

cmd="${1:-}"
[[ -n "$cmd" ]] || feedback_usage
shift

case "$cmd" in
ensure)
  if local_value >/dev/null 2>&1; then
    echo "$KEY is already set in $ENV_FILE; nothing to do"
    exit 0
  fi
  # A new file is created mode 600; an existing .env keeps its mode.
  [[ -f "$ENV_FILE" ]] || (umask 077 && : >"$ENV_FILE")
  python3 - "$ENV_FILE" "$KEY" <<'PY'
import secrets, sys
path, key = sys.argv[1], sys.argv[2]
text = open(path, encoding="utf-8").read()
with open(path, "a", encoding="utf-8") as f:
    f.write(("" if not text or text.endswith("\n") else "\n") + f"{key}={secrets.token_urlsafe(32)}\n")
PY
  echo "generated $KEY into $ENV_FILE (value omitted)"
  ;;

password)
  local_value >/dev/null
  # SCRAM-SHA-256 verifier (RFC 5802 / 7677, the form psql's \password sends). token_urlsafe values
  # are ASCII, so SASLprep is the identity.
  local_value | python3 -c '
import base64, hashlib, hmac, os, sys
pw = sys.stdin.read().encode()
salt, it = os.urandom(16), 4096
salted = hashlib.pbkdf2_hmac("sha256", pw, salt, it)
ck = hmac.new(salted, b"Client Key", "sha256").digest()
sk = hmac.new(salted, b"Server Key", "sha256").digest()
b = lambda x: base64.b64encode(x).decode()
print("\\set ON_ERROR_STOP on")
print(f"ALTER ROLE feedback_writer PASSWORD $v$SCRAM-SHA-256${it}:{b(salt)}${b(hashlib.sha256(ck).digest())}:{b(sk)}$v$;")
' | "${PG[@]}" psql -U postgres -d bifrost_golden_source -X -q
  echo "feedback_writer password set (verifier only); next: $0 secret dev stg prod"
  ;;

secret)
  [[ $# -gt 0 ]] || feedback_usage
  for env in "$@"; do check_env_name "$env"; done
  local_value >/dev/null
  for env in "$@"; do
    local_value | kubectl create secret generic "$SECRET" --namespace "bifrost-$env" \
      --from-file="$KEY=/dev/stdin" --dry-run=client -o json |
      kubectl apply --server-side --field-manager=feedback-writer-secret -f - >/dev/null
    echo "bifrost-$env/$SECRET: $KEY applied (value omitted)"
  done
  ;;

check)
  for env in $(envs_or_all "$@"); do check_env_name "$env"; done
  local_value >/dev/null
  "${PG[@]}" psql -U postgres -d bifrost_golden_source -X -tA -c "SET default_transaction_read_only=on;" -c "
    SELECT 'role feedback_writer: ' || CASE WHEN a.oid IS NULL THEN 'missing'
           WHEN a.rolpassword LIKE 'SCRAM-SHA-256\$%' THEN 'present, password set'
           ELSE 'present, NO password' END
    FROM (SELECT 1) one LEFT JOIN pg_authid a ON a.rolname = 'feedback_writer';" | grep -v '^SET$'
  # Signs in over TCP inside the database pod; the value goes on stdin into a shell variable there.
  if local_value | "${PG[@]}" sh -c 'IFS= read -r PGPASSWORD || true; export PGPASSWORD;
       psql -h localhost -U feedback_writer -d bifrost_golden_source -X -tAc "SELECT 1" >/dev/null 2>&1'; then
    echo "local $KEY signs in as feedback_writer: yes"
  else
    echo "local $KEY signs in as feedback_writer: no"
  fi
  for env in $(envs_or_all "$@"); do
    state=$( { local_value; printf '\n'; kubectl -n "bifrost-$env" get secret "$SECRET" -o json 2>/dev/null || true; } |
      python3 -c '
import base64, json, sys
local, _, rest = sys.stdin.read().partition("\n")
if not rest.strip():
    print("missing"); sys.exit()
raw = (json.loads(rest).get("data") or {}).get(sys.argv[1])
print("no key" if raw is None else "equal to local" if base64.b64decode(raw).decode() == local else "DIFFERS from local")
' "$KEY")
    echo "bifrost-$env/$SECRET: $state"
  done
  ;;

*)
  feedback_usage
  ;;
esac
