#!/usr/bin/env bash
# Sync redis_ib ACL passwords from bifrost-platform-plugin/.env into Trade overlay configs.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PLUGIN_ENV="${PLUGIN_ENV:-$ROOT/../bifrost-platform-plugin/.env}"

if [[ ! -f "$PLUGIN_ENV" ]]; then
  echo "Missing $PLUGIN_ENV — copy from bifrost-platform-plugin/.env.example" >&2
  exit 1
fi
# shellcheck disable=SC1090
source "$PLUGIN_ENV"

DEV_PASS="${REDIS_IB_TRADE_DEV_PASS:?REDIS_IB_TRADE_DEV_PASS missing in plugin .env}"
PROD_PASS="${REDIS_IB_TRADE_PROD_PASS:?REDIS_IB_TRADE_PROD_PASS missing in plugin .env}"

python3 - "$ROOT/k8s/overlays/dev/config/config.dev.yaml" "$DEV_PASS" <<'PY'
import re, sys
from pathlib import Path
path, pw = Path(sys.argv[1]), sys.argv[2]
text = path.read_text(encoding="utf-8")
block = f"""redis_ib:
  enabled: true
  host: redis-ib
  port: 6379
  db: 0
  username: trade-dev
  password: "{pw}"
"""
out, n = re.subn(r"^redis_ib:\n(?:  .+\n)+", block, text, count=1, flags=re.MULTILINE)
if n != 1:
    raise SystemExit(f"redis_ib block not found in {path}")
path.write_text(out, encoding="utf-8")
print(f"Updated {path} redis_ib.password (trade-dev)")
PY

for env in stg prod; do
  cfg="$ROOT/k8s/overlays/${env}/config/config.${env}.yaml"
  python3 - "$cfg" "$PROD_PASS" <<'PY'
import re, sys
from pathlib import Path
path, pw = Path(sys.argv[1]), sys.argv[2]
text = path.read_text(encoding="utf-8")
block = f"""redis_ib:
  enabled: true
  host: redis-ib
  port: 6379
  db: 0
  username: trade-prod
  password: "{pw}"
"""
out, n = re.subn(r"^redis_ib:\n(?:  .+\n)+", block, text, count=1, flags=re.MULTILINE)
if n != 1:
    raise SystemExit(f"redis_ib block not found in {path}")
path.write_text(out, encoding="utf-8")
print(f"Updated {path} redis_ib.password (trade-prod)")
PY
done

echo "redis_ib Trade overlay configs synced from plugin .env"
