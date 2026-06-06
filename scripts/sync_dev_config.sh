#!/usr/bin/env bash
# Sync bifrost-trade-infra/.env → config/config.dev.yaml (postgres, redis, ib, server flags).
# Dev default: host/LAN PG+Redis — not the optional docker-infra profile containers.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ROOT}/.env"
CFG="${ROOT}/config/config.dev.yaml"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing ${ENV_FILE} — run: make ensure-env"
  exit 1
fi

# One-time dev convenience: import Polygon key from legacy engine config when .env still has placeholder.
LEGACY_CFG="${ROOT}/../bifrost-trader-engine/config/config.yaml"
if [[ -f "$LEGACY_CFG" ]]; then
  python3 - "$ENV_FILE" "$LEGACY_CFG" <<'PY'
import re
import sys
from pathlib import Path

env_path = Path(sys.argv[1])
legacy_path = Path(sys.argv[2])
env = env_path.read_text(encoding="utf-8")
current = ""
for line in env.splitlines():
    if line.startswith("POLYGON_API_KEY="):
        current = line.split("=", 1)[1].strip()
        break
if current and current not in ("", "CHANGE_ME"):
    raise SystemExit(0)

legacy = legacy_path.read_text(encoding="utf-8")
m = re.search(
    r"^massive:\s*\n(?:  .+\n)*?  api_key:\s*[\"']?([^\"'\n#]+)",
    legacy,
    re.MULTILINE,
)
if not m:
    raise SystemExit(0)
key = m.group(1).strip().strip('"').strip("'")
if not key or key == "CHANGE_ME":
    raise SystemExit(0)

if re.search(r"^POLYGON_API_KEY=", env, re.MULTILINE):
    env = re.sub(r"^POLYGON_API_KEY=.*$", f"POLYGON_API_KEY={key}", env, count=1, flags=re.MULTILINE)
else:
    env = env.rstrip() + f"\nPOLYGON_API_KEY={key}\n"
env_path.write_text(env, encoding="utf-8")
print(f"Imported POLYGON_API_KEY from {legacy_path} into {env_path}")
PY
fi

# shellcheck disable=SC1090
set -a
source "$ENV_FILE"
set +a

PW="${POSTGRES_PASSWORD:-bifrost_dev}"
PG_USER="${POSTGRES_USER:-bifrost}"
PG_DB="${POSTGRES_DB:-bifrost_dev}"
PG_HOST="${POSTGRES_HOST:-host.docker.internal}"
PG_PORT="${POSTGRES_PORT:-5432}"
REDIS_HOST="${REDIS_HOST:-host.docker.internal}"
REDIS_PORT="${REDIS_PORT:-6379}"
IB_HOST_IP="${IB_HOST:-host.docker.internal}"
SKIP_MONITOR_IB="${BIFROST_SKIP_MONITOR_IB:-true}"

python3 - "$CFG" <<PY
import sys
from pathlib import Path
import re

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

def sub_block(text: str, key: str, body: str) -> str:
    pattern = rf"(^postgres:|^redis:|^ib:|^server:)\n"
    if key == "postgres":
        pattern = r"(^postgres:\n)(?:  .+\n)*"
    elif key == "redis":
        pattern = r"(^redis:\n)(?:  .+\n)*"
    elif key == "ib":
        pattern = r"(^ib:\n)(?:  .+\n)*"
    elif key == "server":
        pattern = r"(^server:\n)(?:  .+\n)*"
    else:
        raise ValueError(key)
    repl = body if body.endswith("\n") else body + "\n"
    out, n = re.subn(pattern, repl, text, count=1, flags=re.MULTILINE)
    if n != 1:
        raise SystemExit(f"Could not update {key} block in {path}")
    return out

pw = """${PW}"""
pg_user = """${PG_USER}"""
pg_db = """${PG_DB}"""
pg_host = """${PG_HOST}"""
pg_port = """${PG_PORT}"""
redis_host = """${REDIS_HOST}"""
redis_port = """${REDIS_PORT}"""
ib_host = """${IB_HOST_IP}"""
skip_ib = """${SKIP_MONITOR_IB}""".lower() in ("1", "true", "yes")

postgres = f"""postgres:
  host: {pg_host}
  port: {pg_port}
  user: {pg_user}
  password: {pw}
  database: {pg_db}
"""

redis = f"""redis:
  enabled: true
  host: {redis_host}
  port: {redis_port}
  db: 0
"""

ib = f"""ib:
  connect_timeout: 60.0
  host:
    ip: {ib_host}
    port_type: tws_paper
    client_id:
      daemon: 110
      listener: 101
      operator: 120
      worker_market: 140
      ingestor: 150
      account_agent: 160
"""

server = f"""server:
  skip_monitor_ib: {str(skip_ib).lower()}
"""

text = sub_block(text, "server", server)
text = sub_block(text, "ib", ib)
text = sub_block(text, "postgres", postgres)
text = sub_block(text, "redis", redis)
path.write_text(text, encoding="utf-8")
print(f"Updated {path} from .env (postgres→{pg_host}, redis→{redis_host}, ib→{ib_host})")
PY

# Remind: ops.worker_profiles + ops.celery.prod_worker_hostnames live in config.dev.yaml (from legacy config.yaml).
LEGACY_ENGINE_CFG="${ROOT}/../bifrost-trader-engine/config/config.yaml"
if [[ -f "$LEGACY_ENGINE_CFG" ]] && ! grep -q 'worker_profiles:' "$CFG" 2>/dev/null; then
  echo "NOTE: add ops.worker_profiles from ${LEGACY_ENGINE_CFG} to ${CFG} (see config.dev.yaml comments)."
fi

INFRA_MODE="${BIFROST_DEV_INFRA:-host}"
if [[ "$INFRA_MODE" == "docker-infra" ]]; then
  echo "Applying password in docker-infra postgres (if up)..."
  docker compose -f "${ROOT}/docker-compose.dev.yml" --profile docker-infra exec -T postgres \
    psql -U "$PG_USER" -d "$PG_DB" -c "ALTER USER ${PG_USER} WITH PASSWORD '${PW}';" 2>/dev/null || \
    echo "SKIP postgres ALTER (docker-infra container not running)"
fi
