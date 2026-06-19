#!/usr/bin/env bash
# Sync Prod K8s overlay: .env → config/config.prod.yaml → k8s/overlays/prod/config/
# External PG @ .80; in-cluster Redis (host: redis); K8s ops profile (local subprocess).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CFG="${ROOT}/config/config.prod.yaml"
OVERLAY_DIR="${ROOT}/k8s/overlays/prod/config"
OVERLAY_CFG="${OVERLAY_DIR}/config.prod.yaml"

"${ROOT}/scripts/sync_prod_config.sh"

python3 - "$CFG" "$OVERLAY_CFG" <<'PY'
import re
import sys
from pathlib import Path

src = Path(sys.argv[1]).read_text(encoding="utf-8")
out_path = Path(sys.argv[2])

def sub_block(text: str, key: str, body: str) -> str:
    patterns = {
        "server": r"(^server:\n)(?:  .+\n)*",
        "redis": r"(^redis:\n)(?:  .+\n)*",
        "ops": r"(^ops:\n)(?:  .+\n)*",
        "ib_operator": r"(^ib_operator:\n)(?:  .+\n)*",
    }
    pattern = patterns[key]
    repl = body if body.endswith("\n") else body + "\n"
    out, n = re.subn(pattern, repl, text, count=1, flags=re.MULTILINE)
    if n != 1:
        raise SystemExit(f"Could not update {key} block")
    return out

skip_ib = False
m = re.search(r"skip_monitor_ib:\s*(\w+)", src)
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

redis = """redis:
  enabled: true
  host: redis
  port: 6379
  db: 0
"""

ops = """ops:
  control_profile: prod
  project_root: /build/bifrost-trade-worker
  socket_project_root: /build/bifrost-trade-socket
  executor_mode: local
  local_control: subprocess
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

ib_operator = """ib_operator:
  enabled: true
  stream: "ib:operator:cmd"
  consumer_group: ib-operator
  result_prefix: "ib:operator:result:"
  health_key: "bifrost:health:ws_ib_operator"
  result_ttl_sec: 300
  request_timeout_sec: 120
  bars_backfill_request_timeout_sec: 7200
  health_refresh_sec: 30
  max_result_bytes: 4194304
  block_ms: 5000
  use_for_celery_bars: false
"""

text = sub_block(src, "server", server)
text = sub_block(text, "redis", redis)
text = sub_block(text, "ops", ops)
if "ib_operator:" not in text:
    text = text.replace("sink: postgres\n", f"sink: postgres\n\n{ib_operator}")
else:
    text = sub_block(text, "ib_operator", ib_operator)
out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(text, encoding="utf-8")
print(f"K8s prod overlay config → {out_path} (PG external, redis in-cluster, ops local)")
PY

cp "${ROOT}/config/config.yaml.example" "${OVERLAY_DIR}/config.yaml.example"
echo "Apply: kubectl apply -k ${ROOT}/k8s/overlays/prod"
echo "Secrets: kubectl apply -f k8s/base/secrets/bifrost-prod-secrets.yaml -n bifrost-prod"
