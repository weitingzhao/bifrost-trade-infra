#!/usr/bin/env bash
# Phase 2C prod stack prep: sync config, build images, start compose, health check.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "=== Phase 2C prod preflight ==="

if [[ ! -f .env ]]; then
  echo "Missing .env — run: make ensure-env"
  exit 1
fi

chmod +x scripts/sync_prod_config.sh scripts/check_prod_stack.sh
./scripts/sync_prod_config.sh

echo "Building production images (requires GITHUB_ORG + git refs in .env)..."
docker compose build

echo "Starting production stack..."
docker compose up -d

./scripts/check_prod_stack.sh

echo "=== Phase 2C prod preflight complete ==="
