.PHONY: up down dev build logs ps shell-postgres shell-redis db-init clean

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

dev:
	$(COMPOSE_DEV) up

dev-down:
	$(COMPOSE_DEV) down

dev-build:
	$(COMPOSE_DEV) build

# ── Database ──────────────────────────────────────────────────────────────────

db-init:
	$(COMPOSE) exec engine python scripts/db/db_refresh_schema.py

db-shell:
	$(COMPOSE) exec postgres psql -U $${POSTGRES_USER} -d $${POSTGRES_DB}

# ── Debug shells ──────────────────────────────────────────────────────────────

shell-engine:
	$(COMPOSE) exec engine bash

shell-redis:
	$(COMPOSE) exec redis redis-cli

# ── Cleanup ───────────────────────────────────────────────────────────────────

clean:
	$(COMPOSE) down -v --remove-orphans
	docker system prune -f
