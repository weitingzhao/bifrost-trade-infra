#!/usr/bin/env bash
# Sync DEV overlay config: .env → config/config.dev.yaml → k8s/overlays/dev/config/
# IB + skip_monitor_ib from .env. postgres.host stays CNPG (phase ④) — not overwritten.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ROOT}/.env"
CFG="${ROOT}/config/config.dev.yaml"
OVERLAY_CFG="${ROOT}/k8s/overlays/dev/config/config.dev.yaml"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing ${ENV_FILE} — copy .env.example and fill IB / POLYGON_API_KEY" >&2
  exit 1
fi

# shellcheck disable=SC1090
set -a
source "$ENV_FILE"
set +a

IB_HOST_IP="${IB_HOST:-192.168.10.30}"
IB_PORT_TYPE="${IB_PORT_TYPE:-tws_paper}"
IB_SECONDARY_HOST="${IB_SECONDARY_HOST:-192.168.10.33}"
IB_SECONDARY_PORT_TYPE="${IB_SECONDARY_PORT_TYPE:-tws_live}"
SKIP_MONITOR_IB="${BIFROST_SKIP_MONITOR_IB:-false}"

CID_DAEMON="${IB_CLIENT_ID_DAEMON:-110}"
CID_LISTENER="${IB_CLIENT_ID_LISTENER:-101}"
CID_OPERATOR="${IB_CLIENT_ID_OPERATOR:-120}"
CID_WORKER="${IB_CLIENT_ID_WORKER:-140}"
CID_INGESTOR="${IB_CLIENT_ID_INGESTOR:-150}"
CID_ACCOUNT="${IB_CLIENT_ID_ACCOUNT:-160}"
CID2_LISTENER="${IB_SECONDARY_CLIENT_ID_LISTENER:-102}"
CID2_OPERATOR="${IB_SECONDARY_CLIENT_ID_OPERATOR:-122}"
CID2_ACCOUNT="${IB_SECONDARY_CLIENT_ID_ACCOUNT:-162}"

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

# Preserve CNPG postgres block from overlay (phase ④); merge IB/server from root config.
python3 - "$CFG" "$OVERLAY_CFG" <<'PY'
import re
import sys
from pathlib import Path

root = Path(sys.argv[1]).read_text(encoding="utf-8")
overlay = Path(sys.argv[2]).read_text(encoding="utf-8")

def extract_block(text: str, key: str) -> str:
    m = re.search(rf"^{key}:\n(?:  .+\n)+", text, re.MULTILINE)
    if not m:
        raise SystemExit(f"missing {key} block")
    return m.group(0)

for key in ("server", "ib"):
    block = extract_block(root, key)
    overlay, n = re.subn(rf"^{key}:\n(?:  .+\n)+", block, overlay, count=1, flags=re.MULTILINE)
    if n != 1:
        raise SystemExit(f"could not merge {key} into overlay")

Path(sys.argv[2]).write_text(overlay, encoding="utf-8")
print(f"Merged server/ib into overlay; postgres.host unchanged (CNPG)")
PY

cp "${ROOT}/config/config.yaml.example" "$(dirname "$OVERLAY_CFG")/config.yaml.example"

echo "Overlay ready: ${OVERLAY_CFG}"
echo "Apply: kubectl apply -k ${ROOT}/k8s/overlays/dev"
