#!/usr/bin/env bash
# Owner only. An Agent must not run this script.
#
# Sync redis_ib ACL passwords from bifrost-platform-plugin/.env into the
# gitignored Trade Secrets under ~/.bifrost-owner/secrets/. This script does
# not read bifrost-trade-infra/.env. It does not write tracked overlay YAML.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PLUGIN_ENV="${PLUGIN_ENV:-$ROOT/../bifrost-platform-plugin/.env}"
OWNER_SECRETS="${BIFROST_OWNER_SECRETS:-${HOME}/.bifrost-owner/secrets}"
mkdir -p "$OWNER_SECRETS"
chmod 700 "$OWNER_SECRETS"

if [[ ! -f "$PLUGIN_ENV" ]]; then
  echo "Missing $PLUGIN_ENV — copy from bifrost-platform-plugin/.env.example" >&2
  exit 1
fi
# shellcheck disable=SC1090
source "$PLUGIN_ENV"

# Each env authenticates as its own redis-ib user (TD-21): trade-prod is PROD's alone.
: "${REDIS_IB_TRADE_DEV_PASS:?REDIS_IB_TRADE_DEV_PASS missing in plugin .env}"
: "${REDIS_IB_TRADE_STG_PASS:?REDIS_IB_TRADE_STG_PASS missing in plugin .env (scripts/redis-ib-env-users.sh acl creates it)}"
: "${REDIS_IB_TRADE_PROD_PASS:?REDIS_IB_TRADE_PROD_PASS missing in plugin .env}"
export REDIS_IB_TRADE_DEV_PASS REDIS_IB_TRADE_STG_PASS REDIS_IB_TRADE_PROD_PASS

python3 - "$OWNER_SECRETS" <<'PY'
import os
import re
import sys
from pathlib import Path

secrets_dir = Path(sys.argv[1])
USERS = {
    "dev": ("trade-dev", os.environ["REDIS_IB_TRADE_DEV_PASS"]),
    "stg": ("trade-stg", os.environ["REDIS_IB_TRADE_STG_PASS"]),
    "prod": ("trade-prod", os.environ["REDIS_IB_TRADE_PROD_PASS"]),
}


def upsert(path: Path, name: str, user: str, pw: str) -> None:
    if path.is_file():
        text = path.read_text(encoding="utf-8")
    else:
        text = (
            "apiVersion: v1\n"
            "kind: Secret\n"
            "metadata:\n"
            f"  name: {name}\n"
            "  labels:\n"
            "    app.kubernetes.io/part-of: bifrost\n"
            "type: Opaque\n"
            "stringData:\n"
        )
    if "stringData:" not in text:
        text = text.rstrip() + "\nstringData:\n"

    def set_key(src: str, key: str, val: str) -> str:
        pat = rf"(^[ \t]*{re.escape(key)}:[ \t]*).*$"
        if re.search(pat, src, flags=re.MULTILINE):
            return re.sub(pat, rf'\1"{val}"', src, count=1, flags=re.MULTILINE)
        # Insert under stringData
        return re.sub(
            r"(^stringData:\n)",
            rf'\1  {key}: "{val}"\n',
            src,
            count=1,
            flags=re.MULTILINE,
        )

    text = set_key(text, "REDIS_IB_USERNAME", user)
    text = set_key(text, "REDIS_IB_PASSWORD", pw)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    os.chmod(path, 0o600)
    print(f"Updated {path} → {user} (password omitted)")


for env, (user, pw) in USERS.items():
    upsert(secrets_dir / f"bifrost-{env}-secrets.yaml", f"bifrost-{env}-secrets", user, pw)
PY

echo "redis_ib Trade Secrets updated from plugin .env (YAML overlays untouched)"
echo "Apply with: python3 scripts/materialize_k8s_trade_secrets.py --apply"
