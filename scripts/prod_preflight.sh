#!/usr/bin/env bash
# Phase 2C prod stack prep: sync config, build images, start compose, health check.
# Optional steps (local or git mode): build | up | health | all (default all)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

STEP="${2:-all}"
if [[ "${1:-}" == "local" || "${1:-}" == "git" ]]; then
  MODE="${1}"
  STEP="${2:-all}"
elif [[ "${1:-}" == "build" || "${1:-}" == "up" || "${1:-}" == "health" ]]; then
  MODE="auto"
  STEP="${1}"
else
  MODE="auto"
  STEP="${2:-all}"
fi

case "$STEP" in
  all|build|up|health) ;;
  *)
    echo "Usage: $0 [local] [build|up|health|all]"
    echo "  local build  — sync config + docker compose build"
    echo "  local up     — compose up -d --no-build + nginx restart"
    echo "  local health — prod-health probes only"
    echo "  local        — full preflight (build + up + health)"
    exit 1
    ;;
esac

echo "=== Phase 2C prod preflight (step=${STEP}) ==="

if [[ ! -f .env ]]; then
  echo "Missing .env — run: make ensure-env"
  exit 1
fi

if [[ "$STEP" == "health" ]]; then
  chmod +x scripts/check_prod_stack.sh
  ./scripts/check_prod_stack.sh
  echo "=== Phase 2C prod health check complete ==="
  exit 0
fi

chmod +x scripts/sync_prod_config.sh scripts/check_prod_stack.sh
./scripts/sync_prod_config.sh

# shellcheck disable=SC1090
set -a
source .env
set +a

COMPOSE_FILES=(-f docker-compose.yml)
BUILD_MODE="git"

if [[ "$MODE" == "local" || "${BIFROST_BUILD_LOCAL:-}" == "1" || "${BIFROST_BUILD_LOCAL:-}" == "true" ]]; then
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

if [[ "$STEP" == "all" || "$STEP" == "build" ]]; then
  echo "Building production images (DOCKER_BUILDKIT=1 recommended)..."
  export DOCKER_BUILDKIT="${DOCKER_BUILDKIT:-1}"
  if [[ "$BUILD_MODE" == "local" ]]; then
    echo "Building shared base layers (build-base profile)..."
    docker compose "${COMPOSE_FILES[@]}" --profile build-base build \
      bifrost-base-worker bifrost-base-socket bifrost-base-api
  fi
  docker compose "${COMPOSE_FILES[@]}" build
fi

if [[ "$STEP" == "all" || "$STEP" == "up" ]]; then
  echo "Starting production stack..."
  if [[ "$STEP" == "up" ]]; then
    docker compose "${COMPOSE_FILES[@]}" up -d --no-build
  else
    docker compose "${COMPOSE_FILES[@]}" up -d
  fi

  # nginx upstream blocks resolve service hostnames at process start; after API
  # containers are recreated their Docker IPs change — restart nginx to re-resolve.
  echo "Restarting nginx (refresh upstream DNS after container recreate)..."
  docker compose "${COMPOSE_FILES[@]}" restart nginx
fi

if [[ "$STEP" == "all" ]]; then
  ./scripts/check_prod_stack.sh
fi

echo "=== Phase 2C prod preflight complete (${BUILD_MODE} build, step=${STEP}) ==="
