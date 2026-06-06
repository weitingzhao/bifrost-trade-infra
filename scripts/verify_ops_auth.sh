#!/usr/bin/env bash
# Verify Ops API auth using operator token from config/config.dev.yaml
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CFG="${ROOT}/config/config.dev.yaml"
OPS_URL="${OPS_URL:-http://localhost:8768}"

TOKEN="$(python3 - "$CFG" <<'PY'
import re
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text(encoding="utf-8")
for tok, role in re.findall(r'- token: "([^"]+)"\s+role: "(\w+)"', text):
    if role == "operator":
        print(tok)
        break
else:
    raise SystemExit("No operator token in ops.auth.tokens")
PY
)"

echo "GET ${OPS_URL}/ops/auth/capabilities (operator token from config.dev.yaml)"
curl -sS -H "Authorization: Bearer ${TOKEN}" "${OPS_URL}/ops/auth/capabilities" | python3 -m json.tool
