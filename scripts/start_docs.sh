#!/usr/bin/env bash
# Start MkDocs handbook — hardware roadmap, Goal, migration sign-off, bifrost-platform.
#
# Usage:
#   ./scripts/start_docs.sh              # http://127.0.0.1:8050 (fixed default)
#   ./scripts/start_docs.sh -p 8051      # override port
#
# Creates .venv-docs/ on first run and installs requirements-docs.txt there.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VENV="$ROOT/.venv-docs"
PY="$VENV/bin/python"

if [[ ! -x "$PY" ]]; then
  echo "Creating docs virtualenv at .venv-docs ..."
  python3 -m venv "$VENV"
fi

if ! "$PY" -c "import mkdocs" 2>/dev/null; then
  echo "Installing MkDocs dependencies ..."
  "$PY" -m pip install -U pip
  "$PY" -m pip install -r requirements-docs.txt
fi

exec "$PY" scripts/run_mkdocs.py -p 8050 "$@"
