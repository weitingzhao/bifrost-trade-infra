#!/usr/bin/env bash
# Owner only. An Agent must not run this script.
#
# Owner-run: the Trade operator / admin tokens every Trade write needs (debt TD-23).
#
# The Trade API refuses a write from a caller below operator, and a process exit
# or an IB disconnect from a caller below admin. The role comes from
# `Authorization: Bearer`, matched against OPS_OPERATOR_TOKEN / OPS_ADMIN_TOKEN in
# bifrost-<env>-secrets; without one the caller is ops.auth.default_role.
#
# No subcommand prints a token. A token leaves this script only through the
# macOS clipboard (`copy`) or into a gitignored local env file (`vite-local`).
#
#   trade-operator-tokens.sh check  <env>             set / missing for both tokens
#   trade-operator-tokens.sh ensure <env>             generate the missing ones, patch the Secret,
#                                                     restart the four api Deployments
#   trade-operator-tokens.sh copy   <env> <operator|admin>
#                                                     put one on the clipboard, to paste into
#                                                     the desk's Operator sign-in
#   trade-operator-tokens.sh vite-local <env>         write the operator token as
#                                                     TRADE_OPERATOR_TOKEN into the frontend's
#                                                     .env.development.local (the :5173 proxy adds it)
#
# <env> is dev, stg or prod. `ensure` never replaces a token that is set:
# rotating one means clearing it in the Secret first, on purpose.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}"
APIS=(api-monitor api-account api-market api-research)

usage() { sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }

[[ $# -ge 2 ]] || usage
cmd="$1"
env="$2"
case "$env" in dev | stg | prod) ;; *) usage ;; esac
ns="bifrost-$env"
secret="bifrost-$env-secrets"

# Reads the Secret's two token keys; prints only "<KEY> set|missing" lines.
token_state() {
  kubectl -n "$ns" get secret "$secret" -o json | python3 -c '
import base64, json, sys
data = json.load(sys.stdin).get("data") or {}
for key in ("OPS_OPERATOR_TOKEN", "OPS_ADMIN_TOKEN"):
    raw = base64.b64decode(data.get(key, "")).decode().strip()
    print(key, "set" if raw and not raw.startswith(("REPLACE", "change-me")) else "missing")
'
}

case "$cmd" in
check)
  token_state
  ;;

ensure)
  missing=$(token_state | awk '$2 == "missing" {print $1}')
  if [[ -z "$missing" ]]; then
    echo "both tokens are set in $ns/$secret; nothing to do"
    exit 0
  fi
  tmp=$(mktemp)
  chmod 600 "$tmp"
  trap 'rm -f "$tmp"' EXIT
  # The patch file holds the new values; it is mode 600 and removed on exit.
  python3 - "$tmp" $missing <<'PY'
import json, secrets, sys
path, keys = sys.argv[1], sys.argv[2:]
with open(path, "w") as f:
    json.dump({"stringData": {k: secrets.token_urlsafe(32) for k in keys}}, f)
PY
  kubectl -n "$ns" patch secret "$secret" --type merge --patch-file "$tmp" >/dev/null
  # The gitignored copy lives in the Owner directory (LANE-W33D). A checkout
  # copy is updated only when the Owner file is not there yet.
  local_file="${BIFROST_OWNER_SECRETS:-${HOME}/.bifrost-owner/secrets}/$secret.yaml"
  if [[ ! -f "$local_file" && -f "$ROOT/k8s/base/secrets/$secret.yaml" ]]; then
    local_file="$ROOT/k8s/base/secrets/$secret.yaml"
  fi
  if [[ -f "$local_file" ]]; then
    python3 - "$tmp" "$local_file" <<'PY'
import json, re, sys
vals = json.load(open(sys.argv[1]))["stringData"]
path = sys.argv[2]
text = open(path, encoding="utf-8").read()
for k, v in vals.items():
    pat = rf"(^[ \t]*{re.escape(k)}:[ \t]*).*$"
    if re.search(pat, text, flags=re.M):
        text = re.sub(pat, lambda m: f'{m.group(1)}"{v}"', text, count=1, flags=re.M)
    else:
        text = re.sub(r"(^stringData:\n)", lambda m: f'{m.group(1)}  {k}: "{v}"\n', text, count=1, flags=re.M)
open(path, "w", encoding="utf-8").write(text)
PY
    echo "updated $local_file (values omitted)"
  fi
  echo "generated: $missing"
  for d in "${APIS[@]}"; do kubectl -n "$ns" rollout restart "deploy/$d" >/dev/null; done
  for d in "${APIS[@]}"; do kubectl -n "$ns" rollout status "deploy/$d" --timeout=180s >/dev/null; done
  echo "restarted ${APIS[*]} in $ns"
  token_state
  ;;

copy)
  [[ $# -eq 3 ]] || usage
  case "$3" in operator) key=OPS_OPERATOR_TOKEN ;; admin) key=OPS_ADMIN_TOKEN ;; *) usage ;; esac
  kubectl -n "$ns" get secret "$secret" -o "jsonpath={.data.$key}" | base64 -d | tr -d '\n' | pbcopy
  echo "$key for $env is on the clipboard: paste it into the desk's Operator sign-in (user centre)"
  ;;

vite-local)
  fe_env="$ROOT/../bifrost-trade-frontend/.env.development.local"
  tok=$(kubectl -n "$ns" get secret "$secret" -o jsonpath='{.data.OPS_OPERATOR_TOKEN}' | base64 -d | tr -d '\n')
  [[ -n "$tok" ]] || { echo "OPS_OPERATOR_TOKEN is missing in $ns; run ensure first" >&2; exit 1; }
  touch "$fe_env"
  chmod 600 "$fe_env"
  TOK="$tok" python3 - "$fe_env" <<'PY'
import os, re, sys
path, tok = sys.argv[1], os.environ["TOK"]
text = open(path, encoding="utf-8").read()
line = f"TRADE_OPERATOR_TOKEN={tok}"
if re.search(r"^TRADE_OPERATOR_TOKEN=", text, flags=re.M):
    text = re.sub(r"^TRADE_OPERATOR_TOKEN=.*$", lambda m: line, text, count=1, flags=re.M)
else:
    text = text.rstrip("\n") + ("\n" if text else "") + line + "\n"
open(path, "w", encoding="utf-8").write(text)
PY
  echo "wrote TRADE_OPERATOR_TOKEN ($env) into $fe_env (value omitted); restart Vite: bdev restart trade-ui"
  ;;

*)
  usage
  ;;
esac
