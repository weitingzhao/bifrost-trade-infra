#!/usr/bin/env bash
# Sync bifrost-trade-infra/.env → config/config.prod.yaml (postgres, redis, ib, server, massive).
# Prod default: LAN PG+Redis — not the optional embedded-infra profile containers.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ROOT}/.env"
CFG="${ROOT}/config/config.prod.yaml"
BASE_CFG="${ROOT}/config/config.yaml"
BASE_EXAMPLE="${ROOT}/config/config.yaml.example"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing ${ENV_FILE} — run: make ensure-env"
  exit 1
fi

if [[ ! -f "$BASE_CFG" ]]; then
  cp "$BASE_EXAMPLE" "$BASE_CFG"
  echo "Created ${BASE_CFG} from config.yaml.example"
fi

# shellcheck disable=SC1090
set -a
source "$ENV_FILE"
set +a

PW="${POSTGRES_PASSWORD:?POSTGRES_PASSWORD required in .env for prod sync}"
PG_USER="${POSTGRES_USER:-bifrost}"
PG_DB="${POSTGRES_DB:-bifrost_prod}"
PG_HOST="${POSTGRES_HOST:-192.168.10.80}"
PG_PORT="${POSTGRES_PORT:-5432}"
REDIS_HOST="${REDIS_HOST:-192.168.10.70}"
REDIS_PORT="${REDIS_PORT:-6379}"
IB_HOST_IP="${IB_HOST:-192.168.10.30}"
IB_PORT_TYPE="${IB_PORT_TYPE:-tws_live}"
SKIP_MONITOR_IB="${BIFROST_SKIP_MONITOR_IB:-false}"
POLYGON_KEY="${POLYGON_API_KEY:-${MASSIVE_API_KEY:-CHANGE_ME}}"

CID_DAEMON="${IB_CLIENT_ID_DAEMON:-1}"
CID_LISTENER="${IB_CLIENT_ID_LISTENER:-2}"
CID_OPERATOR="${IB_CLIENT_ID_OPERATOR:-3}"
CID_WORKER="${IB_CLIENT_ID_WORKER:-4}"
CID_INGESTOR="${IB_CLIENT_ID_INGESTOR:-5}"
CID_ACCOUNT="${IB_CLIENT_ID_ACCOUNT:-6}"

python3 - "$CFG" <<PY
import sys
from pathlib import Path
import re

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

def sub_block(text: str, key: str, body: str) -> str:
    if key == "postgres":
        pattern = r"(^postgres:\n)(?:  .+\n)*"
    elif key == "redis":
        pattern = r"(^redis:\n)(?:  .+\n)*"
    elif key == "ib":
        pattern = r"(^ib:\n)(?:  .+\n)*"
    elif key == "server":
        pattern = r"(^server:\n)(?:  .+\n)*"
    elif key == "massive":
        pattern = r"(^massive:\n)(?:  .+\n)*"
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
port_type = """${IB_PORT_TYPE}"""
skip_ib = """${SKIP_MONITOR_IB}""".lower() in ("1", "true", "yes")
polygon = """${POLYGON_KEY}"""

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

cid_daemon = """${CID_DAEMON}"""
cid_listener = """${CID_LISTENER}"""
cid_operator = """${CID_OPERATOR}"""
cid_worker = """${CID_WORKER}"""
cid_ingestor = """${CID_INGESTOR}"""
cid_account = """${CID_ACCOUNT}"""

ib = f"""ib:
  connect_timeout: 60.0
  host:
    ip: {ib_host}
    port_type: {port_type}
    client_id:
      daemon: {cid_daemon}
      listener: {cid_listener}
      operator: {cid_operator}
      worker_market: {cid_worker}
      ingestor: {cid_ingestor}
      account_agent: {cid_account}
"""

server = f"""server:
  skip_monitor_ib: {str(skip_ib).lower()}
"""

massive = f"""massive:
  api_key: {polygon}
"""

text = sub_block(text, "server", server)
text = sub_block(text, "ib", ib)
text = sub_block(text, "postgres", postgres)
text = sub_block(text, "redis", redis)
text = sub_block(text, "massive", massive)
path.write_text(text, encoding="utf-8")
print(f"Updated {path} from .env (postgres→{pg_host}/{pg_db}, redis→{redis_host}, ib→{ib_host})")
PY

INFRA_MODE="${BIFROST_PROD_INFRA:-host}"
if [[ "$INFRA_MODE" == "embedded-infra" ]]; then
  echo "Applying password in embedded-infra postgres (if up)..."
  docker compose --profile embedded-infra exec -T postgres \
    psql -U "$PG_USER" -d "$PG_DB" -c "ALTER USER ${PG_USER} WITH PASSWORD '${PW}';" 2>/dev/null || \
    echo "SKIP postgres ALTER (embedded-infra container not running)"
fi
