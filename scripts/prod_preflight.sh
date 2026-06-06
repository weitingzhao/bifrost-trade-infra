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

# shellcheck disable=SC1090
set -a
source .env
set +a

COMPOSE_FILES=(-f docker-compose.yml)
BUILD_MODE="git"

if [[ "${1:-}" == "local" || "${BIFROST_BUILD_LOCAL:-}" == "1" || "${BIFROST_BUILD_LOCAL:-}" == "true" ]]; then
  BUILD_MODE="local"
  COMPOSE_FILES+=(-f docker-compose.local.yml)
  echo "Build mode: local monorepo (sibling repos, no GitHub pip)"
elif [[ "${GITHUB_ORG:-}" == "YOUR_ORG" || -z "${GITHUB_ORG:-}" ]]; then
  echo "GITHUB_ORG not set — using local monorepo build."
  echo "  (Set GITHUB_ORG for git pip builds on future prod cluster; or BIFROST_BUILD_LOCAL=1 in .env)"
  BUILD_MODE="local"
  COMPOSE_FILES+=(-f docker-compose.local.yml)
else
  echo "Build mode: git pip (GITHUB_ORG=${GITHUB_ORG}, core=${BIFROST_CORE_REF:-main})"
fi

echo "Building production images..."
docker compose "${COMPOSE_FILES[@]}" build

echo "Starting production stack..."
docker compose "${COMPOSE_FILES[@]}" up -d

./scripts/check_prod_stack.sh

echo "=== Phase 2C prod preflight complete (${BUILD_MODE} build) ==="
