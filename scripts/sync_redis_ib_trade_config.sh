#!/usr/bin/env bash
# Sync redis_ib ACL passwords from bifrost-platform-plugin/.env into gitignored Trade Secrets.
# Does NOT write tracked overlay YAML (ConfigMap) — secrets go via REDIS_IB_* envFrom.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PLUGIN_ENV="${PLUGIN_ENV:-$ROOT/../bifrost-platform-plugin/.env}"

if [[ ! -f "$PLUGIN_ENV" ]]; then
  echo "Missing $PLUGIN_ENV — copy from bifrost-platform-plugin/.env.example" >&2
  exit 1
fi
# shellcheck disable=SC1090
source "$PLUGIN_ENV"

PROD_PASS="${REDIS_IB_TRADE_PROD_PASS:?REDIS_IB_TRADE_PROD_PASS missing in plugin .env}"
USER_NAME="${REDIS_IB_TRADE_PROD_USER:-trade-prod}"

python3 - "$ROOT" "$PROD_PASS" "$USER_NAME" <<'PY'
import os
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
pw = sys.argv[2]
user = sys.argv[3]


def upsert(path: Path, name: str) -> None:
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
    print(f"Updated {path} REDIS_IB_PASSWORD (value omitted)")


for env in ("dev", "stg", "prod"):
    upsert(root / f"k8s/base/secrets/bifrost-{env}-secrets.yaml", f"bifrost-{env}-secrets")
PY

echo "redis_ib Trade Secrets updated from plugin .env (YAML overlays untouched)"
echo "Apply with: python3 scripts/materialize_k8s_trade_secrets.py --apply"
