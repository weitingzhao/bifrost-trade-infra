.PHONY: up down build logs ps prod-build prod-build-local prod-base-local prod-up-local prod-rebuild-local prod-rebuild-local-api prod-pull-base-images prod-preflight prod-preflight-local prod-preflight-local-build prod-preflight-local-up prod-preflight-local-health prod-health prod-down-local prod-embedded-infra sync-prod-config verify-2c-a1 dev dev-docker-infra dev-down dev-build dev-reinstall-deps dev-preflight dev-health verify-domain-apis verify-wave-a-sessions switch-cutover-domain signoff-start check-cutover-env sync-dev-config sync-dev-db-password db-init db-init-dev db-shell shell-redis clean

COMPOSE        = docker compose
COMPOSE_LOCAL  = docker compose -f docker-compose.yml -f docker-compose.local.yml
COMPOSE_DEV    = docker compose -f docker-compose.dev.yml

# ── Production ────────────────────────────────────────────────────────────────

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

build: prod-build

prod-build: ensure-env sync-prod-config
	$(COMPOSE) build

prod-build-local: ensure-env sync-prod-config prod-base-local
	export DOCKER_BUILDKIT=$${DOCKER_BUILDKIT:-1}; \
	$(COMPOSE_LOCAL) build

# Shared deps layers only (core/worker/socket). Run after pyproject or base Dockerfile changes.
prod-base-local: ensure-env
	export DOCKER_BUILDKIT=$${DOCKER_BUILDKIT:-1}; \
	$(COMPOSE_LOCAL) --profile build-base build \
		bifrost-base-worker bifrost-base-socket bifrost-base-api

# Start prod-local stack without rebuilding images.
prod-up-local: ensure-env sync-prod-config
	$(COMPOSE_LOCAL) up -d --no-build
	$(COMPOSE_LOCAL) restart nginx

# Rebuild one service, recreate it, refresh nginx upstream DNS.
# Usage: make prod-rebuild-local SERVICE=api-monitor
prod-rebuild-local: ensure-env sync-prod-config
ifndef SERVICE
	$(error SERVICE is required, e.g. make prod-rebuild-local SERVICE=api-monitor)
endif
	export DOCKER_BUILDKIT=$${DOCKER_BUILDKIT:-1}; \
	$(COMPOSE_LOCAL) build $(SERVICE)
	$(COMPOSE_LOCAL) up -d --no-build $(SERVICE)
	$(COMPOSE_LOCAL) restart nginx

# Rebuild all 9 API domains (shared bifrost-api:local image) after api-only code changes.
prod-rebuild-local-api: ensure-env sync-prod-config
	export DOCKER_BUILDKIT=$${DOCKER_BUILDKIT:-1}; \
	$(COMPOSE_LOCAL) build api-monitor
	$(COMPOSE_LOCAL) up -d --no-build \
		api-monitor api-massive api-docs api-ops api-trading api-strategy \
		api-portfolio api-market api-research
	$(COMPOSE_LOCAL) restart nginx

prod-pull-base-images:
	docker pull python:3.11-slim
	docker pull node:20-slim
	docker pull nginx:alpine
	docker pull postgres:16-alpine
	docker pull redis:7-alpine

prod-preflight:
	@chmod +x scripts/prod_preflight.sh
	@./scripts/prod_preflight.sh

prod-preflight-local:
	@chmod +x scripts/prod_preflight.sh
	@./scripts/prod_preflight.sh local

prod-preflight-local-build: ensure-env sync-prod-config
	@chmod +x scripts/prod_preflight.sh
	@./scripts/prod_preflight.sh local build

prod-preflight-local-up: ensure-env sync-prod-config
	@chmod +x scripts/prod_preflight.sh
	@./scripts/prod_preflight.sh local up

prod-preflight-local-health:
	@chmod +x scripts/prod_preflight.sh
	@./scripts/prod_preflight.sh local health

prod-down-local:
	$(COMPOSE_LOCAL) down

prod-health:
	@chmod +x scripts/check_prod_stack.sh
	@./scripts/check_prod_stack.sh

# Phase 2C-A.1 — Docker control plane (Ops executor + market-ingest). See docs/PHASE2C_A1_DOCKER_CONTROL_PLANE.md
verify-2c-a1:
	@chmod +x scripts/verify_2c_a1_control_plane.sh
	@./scripts/verify_2c_a1_control_plane.sh

sync-prod-config:
	@chmod +x scripts/sync_prod_config.sh
	@./scripts/sync_prod_config.sh

# Optional isolated PG+Redis for prod compose smoke (greenfield/CI).
prod-embedded-infra: ensure-env sync-prod-config
	$(COMPOSE) --profile embedded-infra up -d postgres redis
	$(COMPOSE) up -d
	@echo "Prod stack with embedded-infra. Run: make prod-health"

logs:
	$(COMPOSE) logs -f

ps:
	$(COMPOSE) ps

# ── Development ───────────────────────────────────────────────────────────────

ensure-env:
	@test -f .env || (cp .env.example .env && echo "Created .env from .env.example — review POSTGRES_* / REDIS_* before prod.")

sync-dev-config:
	@chmod +x scripts/sync_dev_config.sh
	@./scripts/sync_dev_config.sh

# Default dev: app containers only; PG/Redis from host or LAN (.env → config.dev.yaml).
dev: ensure-env sync-dev-config
	$(COMPOSE_DEV) up -d
	@echo "Dev stack starting (host/LAN PG+Redis). Run: make dev-health"

# Optional isolated empty PG+Redis in Docker (CI / first-time schema only).
dev-docker-infra: ensure-env sync-dev-config
	$(COMPOSE_DEV) --profile docker-infra up -d postgres redis
	$(COMPOSE_DEV) up -d
	@echo "Dev stack with docker-infra PG+Redis. Run: make dev-health"

dev-attach: ensure-env sync-dev-config
	$(COMPOSE_DEV) up

dev-down:
	$(COMPOSE_DEV) --profile docker-infra down

dev-build: ensure-env
	$(COMPOSE_DEV) build

# Force editable reinstall on next container start (e.g. after pyproject dependency change).
dev-reinstall-deps:
	$(COMPOSE_DEV) down || true
	docker volume rm bifrost-trade-infra_dev-install-state 2>/dev/null || true
	@echo "Cleared dev-install-state volume. Run: make dev"

dev-logs:
	$(COMPOSE_DEV) logs -f

dev-health:
	@chmod +x scripts/check_dev_stack.sh
	@./scripts/check_dev_stack.sh

verify-ops-auth:
	@chmod +x scripts/verify_ops_auth.sh
	@./scripts/verify_ops_auth.sh

dev-preflight:
	@chmod +x scripts/dev_preflight.sh
	@./scripts/dev_preflight.sh

verify-domain-apis:
	@chmod +x scripts/verify_domain_apis.sh
	@./scripts/verify_domain_apis.sh

verify-wave-a-sessions:
	@chmod +x scripts/verify_wave_a_sessions.sh
	@./scripts/verify_wave_a_sessions.sh

# Usage: make switch-cutover-domain DOMAIN=docs MODE=legacy|new  |  DOMAIN=all-new
switch-cutover-domain:
	@chmod +x scripts/switch_cutover_domain.sh
	@./scripts/switch_cutover_domain.sh $(DOMAIN) $(MODE)

# Usage: make signoff-start SESSION=1  (backend prep; frontend: ../bifrost-trade-frontend/signoff-dev.sh)
signoff-start:
	@chmod +x scripts/signoff_start.sh
	@./scripts/signoff_start.sh $(if $(SESSION),$(SESSION),1)

check-cutover-env:
	@chmod +x scripts/check_cutover_env.sh
	@./scripts/check_cutover_env.sh

# ── Database ──────────────────────────────────────────────────────────────────

db-init:
	cd ../bifrost-trade-core && BIFROST_CONFIG=../bifrost-trade-core/config/config.yaml.example python scripts/db/db_refresh_schema.py

sync-dev-db-password: sync-dev-config

db-init-dev: sync-dev-config
	$(COMPOSE_DEV) exec -T -e BIFROST_CONFIG=/app/config/config.dev.yaml api-monitor \
		python /workspace/bifrost-trade-core/scripts/db/db_refresh_schema.py

db-shell:
	$(COMPOSE) exec postgres psql -U $${POSTGRES_USER:-bifrost} -d $${POSTGRES_DB:-bifrost_dev}

# ── Debug shells ──────────────────────────────────────────────────────────────

shell-redis:
	$(COMPOSE) exec redis redis-cli

# ── Cleanup ───────────────────────────────────────────────────────────────────

# WARNING: prune removes Docker builder cache — avoid during active 2C signoff rebuild loops.
clean:
	$(COMPOSE) down -v --remove-orphans
	docker system prune -f
