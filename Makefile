.PHONY: up down dev dev-down dev-build dev-health check-cutover-env build logs ps db-init db-init-dev db-shell shell-redis clean

COMPOSE      = docker compose
COMPOSE_DEV  = docker compose -f docker-compose.dev.yml

# ── Production ────────────────────────────────────────────────────────────────

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

build:
	$(COMPOSE) build

logs:
	$(COMPOSE) logs -f

ps:
	$(COMPOSE) ps

# ── Development ───────────────────────────────────────────────────────────────

ensure-env:
	@test -f .env || (cp .env.example .env && echo "Created .env from .env.example — review POSTGRES_* / REDIS_* before prod.")

dev: ensure-env
	$(COMPOSE_DEV) up -d
	@echo "Dev stack starting in background. Run: make dev-health  (or: make dev-logs)"

dev-attach: ensure-env
	$(COMPOSE_DEV) up

dev-down:
	$(COMPOSE_DEV) down

dev-build: ensure-env
	$(COMPOSE_DEV) build

dev-logs:
	$(COMPOSE_DEV) logs -f

dev-health:
	@chmod +x scripts/check_dev_stack.sh
	@./scripts/check_dev_stack.sh

check-cutover-env:
	@chmod +x scripts/check_cutover_env.sh
	@./scripts/check_cutover_env.sh

# ── Database ──────────────────────────────────────────────────────────────────

db-init:
	cd ../bifrost-trade-core && BIFROST_CONFIG=../bifrost-trade-core/config/config.yaml.example python scripts/db/db_refresh_schema.py

db-init-dev:
	$(COMPOSE_DEV) exec -T postgres psql -U $${POSTGRES_USER:-bifrost} -d $${POSTGRES_DB:-bifrost_dev} -c "SELECT 1" >/dev/null
	cd ../bifrost-trade-core && BIFROST_CONFIG=../bifrost-trade-core/config/config.yaml.example python scripts/db/db_refresh_schema.py

db-shell:
	$(COMPOSE) exec postgres psql -U $${POSTGRES_USER:-bifrost} -d $${POSTGRES_DB:-bifrost_dev}

# ── Debug shells ──────────────────────────────────────────────────────────────

shell-redis:
	$(COMPOSE) exec redis redis-cli

# ── Cleanup ───────────────────────────────────────────────────────────────────

clean:
	$(COMPOSE) down -v --remove-orphans
	docker system prune -f
