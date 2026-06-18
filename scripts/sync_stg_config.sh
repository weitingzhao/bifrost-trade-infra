#!/usr/bin/env bash
# Sync STG overlay config: .env → config/config.stg.yaml → k8s/overlays/stg/config/
# In-cluster PG/Redis hosts are preserved. IB + skip_monitor_ib from .env.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ROOT}/.env"
CFG="${ROOT}/config/config.stg.yaml"
OVERLAY_CFG="${ROOT}/k8s/overlays/stg/config/config.stg.yaml"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing ${ENV_FILE} — copy .env.example and fill IB / POLYGON_API_KEY" >&2
  exit 1
fi

# shellcheck disable=SC1090
set -a
source "$ENV_FILE"
set +a

IB_HOST_IP="${IB_HOST:-192.168.10.30}"
IB_PORT_TYPE="${IB_PORT_TYPE:-tws_live}"
IB_SECONDARY_HOST="${IB_SECONDARY_HOST:-192.168.10.33}"
IB_SECONDARY_PORT_TYPE="${IB_SECONDARY_PORT_TYPE:-tws_live}"
SKIP_MONITOR_IB="${BIFROST_SKIP_MONITOR_IB:-false}"

# STG K3s client_id block (210 range — isolated from prod 10 / dev 110)
CID_DAEMON="${STG_IB_CLIENT_ID_DAEMON:-210}"
CID_LISTENER="${STG_IB_CLIENT_ID_LISTENER:-201}"
CID_OPERATOR="${STG_IB_CLIENT_ID_OPERATOR:-220}"
CID_WORKER="${STG_IB_CLIENT_ID_WORKER:-240}"
CID_INGESTOR="${STG_IB_CLIENT_ID_INGESTOR:-250}"
CID_ACCOUNT="${STG_IB_CLIENT_ID_ACCOUNT:-260}"
CID2_LISTENER="${STG_IB_SECONDARY_CLIENT_ID_LISTENER:-202}"
CID2_OPERATOR="${STG_IB_SECONDARY_CLIENT_ID_OPERATOR:-222}"
CID2_ACCOUNT="${STG_IB_SECONDARY_CLIENT_ID_ACCOUNT:-262}"

python3 - "$CFG" <<PY
import sys
from pathlib import Path
import re

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

def sub_block(text: str, key: str, body: str) -> str:
    patterns = {
        "server": r"(^server:\n)(?:  .+\n)*",
        "ib": r"(^ib:\n)(?:  .+\n)*",
    }
    pattern = patterns[key]
    repl = body if body.endswith("\n") else body + "\n"
    out, n = re.subn(pattern, repl, text, count=1, flags=re.MULTILINE)
    if n != 1:
        raise SystemExit(f"Could not update {key} block in {path}")
    return out

ib_host = """${IB_HOST_IP}"""
port_type = """${IB_PORT_TYPE}"""
ib2_host = """${IB_SECONDARY_HOST}"""
ib2_port_type = """${IB_SECONDARY_PORT_TYPE}"""
skip_ib = """${SKIP_MONITOR_IB}""".lower() in ("1", "true", "yes")
cid_daemon = """${CID_DAEMON}"""
cid_listener = """${CID_LISTENER}"""
cid_operator = """${CID_OPERATOR}"""
cid_worker = """${CID_WORKER}"""
cid_ingestor = """${CID_INGESTOR}"""
cid_account = """${CID_ACCOUNT}"""
cid2_listener = """${CID2_LISTENER}"""
cid2_operator = """${CID2_OPERATOR}"""
cid2_account = """${CID2_ACCOUNT}"""

secondary_block = ""
if ib2_host.strip():
    secondary_block = f"""  secondary:
    ip: {ib2_host.strip()}
    port_type: {ib2_port_type}
    client_id:
      listener: {cid2_listener}
      operator: {cid2_operator}
      account_agent: {cid2_account}
"""

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
{secondary_block}"""

server = f"""server:
  skip_monitor_ib: {str(skip_ib).lower()}
  architecture:
    monitor_port: 8765
    ops_port: 8768
    docs_port: 8767
  account:
    trading_port: 8769
    portfolio_port: 8771
  research:
    research_port: 8773
    market_port: 8772
    strategy_port: 8770
  feed:
    massive_port: 8766
"""

text = sub_block(text, "server", server)
text = sub_block(text, "ib", ib)
path.write_text(text, encoding="utf-8")
print(f"Updated {path} (ib→{ib_host}, skip_monitor_ib={str(skip_ib).lower()})")
PY

mkdir -p "$(dirname "$OVERLAY_CFG")"
cp "$CFG" "$OVERLAY_CFG"
cp "${ROOT}/config/config.yaml.example" "$(dirname "$OVERLAY_CFG")/config.yaml.example"
echo "Copied → ${OVERLAY_CFG} + config.yaml.example"
echo "Apply to cluster: kubectl apply -k ${ROOT}/k8s/overlays/stg"
echo "Secrets: kubectl apply -f k8s/base/secrets/bifrost-stg-secrets.yaml -n bifrost-stg (from .example)"
