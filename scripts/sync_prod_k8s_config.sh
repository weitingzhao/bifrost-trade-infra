#!/usr/bin/env bash
# Sync Prod K8s overlay: .env → config/config.prod.yaml; merge IB/server into overlay only.
# Postgres/redis_queue stay CNPG @ data NS — never copy compose .env PG into overlay.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CFG="${ROOT}/config/config.prod.yaml"
OVERLAY_DIR="${ROOT}/k8s/overlays/prod/config"
OVERLAY_CFG="${OVERLAY_DIR}/config.prod.yaml"

"${ROOT}/scripts/sync_prod_config.sh"
"${ROOT}/scripts/sync_prod_overlay_config.sh"

python3 - "$CFG" "$OVERLAY_CFG" <<'PY'
import re
import sys
from pathlib import Path

root = Path(sys.argv[1]).read_text(encoding="utf-8")
overlay_path = Path(sys.argv[2])
overlay = overlay_path.read_text(encoding="utf-8")

def extract_block(text: str, key: str) -> str:
    m = re.search(rf"^{key}:\n(?:  .+\n)+", text, re.MULTILINE)
    if not m:
        raise SystemExit(f"missing {key} block")
    return m.group(0)

def sub_block(text: str, key: str, body: str) -> str:
    repl = body if body.endswith("\n") else body + "\n"
    out, n = re.subn(rf"^{key}:\n(?:  .+\n)+", repl, text, count=1, flags=re.MULTILINE)
    if n != 1:
        raise SystemExit(f"could not merge {key} into overlay")
    return out

skip_ib = False
m = re.search(r"skip_monitor_ib:\s*(\w+)", root)
if m:
    skip_ib = m.group(1).lower() in ("1", "true", "yes")

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

ops = """ops:
  control_profile: prod
  executor_mode: kubernetes
  kubernetes:
    namespace: bifrost-prod
  celery:
    prod_worker_hostnames:
      - celery-worker
  worker_profiles:
    stocks_ib:
      queues: ["stocks_ib"]
      max_worker_instances: 1
    options_massive:
      queues: ["options_massive"]
      pool: solo
      max_worker_instances: 4
    options_massive_high:
      queues: ["options_massive_high"]
      pool: solo
      max_worker_instances: 1
    stocks_massive:
      queues: ["stocks_massive"]
      pool: solo
      max_worker_instances: 2
    stocks_massive_high:
      queues: ["stocks_massive_high"]
      pool: solo
      max_worker_instances: 1
  auth:
    default_role: operator
    allow_unauthenticated_reads: false
    tokens: []
  audit:
    persist: true
"""

for key in ("server", "ib", "massive"):
    overlay = sub_block(overlay, key, extract_block(root, key))
overlay = sub_block(overlay, "ops", ops)
overlay_path.write_text(overlay, encoding="utf-8")
print(f"K8s prod overlay config → {overlay_path} (CNPG preserved; ops kubernetes)")
PY

cp "${ROOT}/config/config.yaml.example" "${OVERLAY_DIR}/config.yaml.example"
echo "Apply: kubectl apply -k ${ROOT}/k8s/overlays/prod"
echo "Secrets: kubectl apply -f k8s/base/secrets/bifrost-prod-secrets.yaml -n bifrost-prod"
