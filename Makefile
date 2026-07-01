.PHONY: up down build logs ps prod-build prod-build-local prod-base-local prod-up-local prod-rebuild-local prod-rebuild-local-api prod-pull-base-images prod-preflight prod-preflight-local prod-preflight-local-build prod-preflight-local-up prod-preflight-local-health prod-health release-gate prod-down-local prod-embedded-infra sync-prod-config sync-stg-config verify-2c-a1 local-prod-final-gate dev dev-docker-infra dev-down dev-build dev-reinstall-deps dev-preflight dev-health verify-domain-apis verify-wave-a-sessions switch-cutover-domain signoff-start check-cutover-env sync-dev-config sync-dev-db-password db-init db-init-dev db-shell shell-redis k3s-install-remote k3s-install-remote-run k3s-verify-remote k3s-fetch-kubeconfig k3s-install-metrics-remote k3s-install-argocd k3s-verify-argocd k3s-install-cicd-stack k3s-verify-cicd-stack k3s-install-bifrost-stg k3s-verify-bifrost-stg k3s-install-gitea-persistent k3s-bootstrap-gitea-mirrors k3s-sync-gitea-mirrors k3s-deliver-stg k3s-install-ci-frontend-git k3s-verify-ci-frontend-git k3s-install-ci-frontend-build k3s-verify-ci-frontend-build k3s-install-ci-deliver-stg k3s-verify-ci-deliver-stg k3s-install-phase-b-stg k3s-verify-phase-b-stg k3s-verify-phase-b-stg-v2 k3s-join-agent-remote clean docs docs-build

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

release-gate:
	@chmod +x scripts/release_gate.sh
	@./scripts/release_gate.sh

local-prod-final-gate:
	@chmod +x scripts/local_prod_final_gate.sh
	@./scripts/local_prod_final_gate.sh

local-prod-final-owner:
	@chmod +x scripts/local_prod_final_owner.sh
	@./scripts/local_prod_final_owner.sh $(SESSION)

# Phase 2C-A.1 — Docker control plane (Ops executor + market-ingest). See docs/PHASE2C_A1_DOCKER_CONTROL_PLANE.md
verify-2c-a1:
	@chmod +x scripts/verify_2c_a1_control_plane.sh
	@./scripts/verify_2c_a1_control_plane.sh

sync-prod-config:
	@chmod +x scripts/sync_prod_config.sh
	@./scripts/sync_prod_config.sh

sync-prod-k8s-config:
	@chmod +x scripts/sync_prod_k8s_config.sh
	@./scripts/sync_prod_k8s_config.sh

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

# ── Documentation (MkDocs) ────────────────────────────────────────────────────

docs:
	./scripts/start_docs.sh

docs-build:
	python -c "from scripts.run_mkdocs import _ensure_doc_symlinks; _ensure_doc_symlinks()"
	python -m mkdocs build

# ── K3s bootstrap (LAN server — requires interactive sudo on target) ─────────

K3S_HOST ?= vision@192.168.10.73
K3S_NODE_IP ?= 192.168.10.73
# install-server.sh sets kubeconfig mode 644 — vision can kubectl without sudo over SSH
K3S_REMOTE_KUBECTL = KUBECONFIG=/etc/rancher/k3s/k3s.yaml k3s kubectl

k3s-install-remote:
	@chmod +x scripts/k3s/install-server.sh scripts/k3s/fetch-kubeconfig.sh
	scp scripts/k3s/install-server.sh $(K3S_HOST):~/install-k3s-server.sh
	@echo "Run on server (interactive sudo): ssh -t $(K3S_HOST) 'sudo bash ~/install-k3s-server.sh'"

k3s-install-remote-run:
	@chmod +x scripts/k3s/install-server.sh
	scp scripts/k3s/install-server.sh $(K3S_HOST):~/install-k3s-server.sh
	ssh -t $(K3S_HOST) 'sudo bash ~/install-k3s-server.sh'

k3s-verify-remote:
	ssh $(K3S_HOST) '$(K3S_REMOTE_KUBECTL) get nodes -o wide && $(K3S_REMOTE_KUBECTL) get ns | grep -E "cicd|bifrost|data"'

k3s-fetch-kubeconfig:
	@chmod +x scripts/k3s/fetch-kubeconfig.sh
	K3S_NODE_IP=$(K3S_NODE_IP) ./scripts/k3s/fetch-kubeconfig.sh $(K3S_HOST)

# Layer A — metrics-server (uses local kubeconfig; cluster API @ K3S_NODE_IP)
KUBECONFIG ?= $(HOME)/.kube/bifrost-k3s.yaml

k3s-install-metrics-remote:
	@chmod +x scripts/k3s/install-metrics-server.sh
	KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/install-metrics-server.sh

# NAS NFS — StorageClass nfs-hot / nfs-cold (UGREEN @ 192.168.10.20; run install-nfs-common-nodes.sh first)
k3s-install-nfs-common-nodes:
	@chmod +x scripts/k3s/install-nfs-common-nodes.sh
	./scripts/k3s/install-nfs-common-nodes.sh

k3s-install-nfs-provisioner:
	@chmod +x scripts/k3s/install-nfs-provisioner.sh
	KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/install-nfs-provisioner.sh

k3s-verify-nfs-provisioner:
	@chmod +x scripts/k3s/verify-nfs-provisioner.sh
	KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/verify-nfs-provisioner.sh

# Data layer phase ① — CNPG operator + bifrost-postgres @ data namespace (D2-prime)
k3s-label-postgres-node:
	@chmod +x scripts/k3s/label-postgres-node.sh
	KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/label-postgres-node.sh

k3s-install-cnpg-operator:
	@chmod +x scripts/k3s/install-cnpg-operator.sh
	KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/install-cnpg-operator.sh

k3s-install-data-layer-phase0:
	@chmod +x scripts/k3s/install-data-layer-phase0.sh scripts/k3s/label-postgres-node.sh scripts/k3s/install-cnpg-operator.sh
	KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/install-data-layer-phase0.sh

k3s-verify-data-layer-phase0:
	@chmod +x scripts/k3s/verify-data-layer-phase0.sh
	KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/verify-data-layer-phase0.sh

# Data layer phase ② — CNPG instances=2 + MinIO @ nfs-hot + barman WAL backup
k3s-label-postgres-standby-node:
	@chmod +x scripts/k3s/label-postgres-standby-node.sh
	KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/label-postgres-standby-node.sh

k3s-install-data-layer-phase1:
	@chmod +x scripts/k3s/install-data-layer-phase1.sh scripts/k3s/label-postgres-node.sh scripts/k3s/label-postgres-standby-node.sh
	KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/install-data-layer-phase1.sh

k3s-verify-data-layer-phase1:
	@chmod +x scripts/k3s/verify-data-layer-phase1.sh
	KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/verify-data-layer-phase1.sh

k3s-switchover-postgres-primary:
	@chmod +x scripts/k3s/switchover-postgres-primary.sh
	KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/switchover-postgres-primary.sh

# Data layer phase ③ — STG cutover to CNPG @ data NS
k3s-migrate-stg-postgres-to-cnpg:
	@chmod +x scripts/k3s/migrate-stg-postgres-to-cnpg.sh
	KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/migrate-stg-postgres-to-cnpg.sh

k3s-cutover-stg-data-layer-phase2:
	@chmod +x scripts/k3s/cutover-stg-data-layer-phase2.sh scripts/k3s/migrate-stg-postgres-to-cnpg.sh scripts/k3s/verify-data-layer-phase2-stg.sh scripts/k3s/verify-data-layer-phase1.sh scripts/sync_stg_config.sh
	KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/cutover-stg-data-layer-phase2.sh

k3s-verify-data-layer-phase2-stg:
	@chmod +x scripts/k3s/verify-data-layer-phase2-stg.sh
	KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/verify-data-layer-phase2-stg.sh

# Data layer phase ④ — DEV cutover to CNPG @ data NS
k3s-migrate-dev-postgres-to-cnpg:
	@chmod +x scripts/k3s/migrate-dev-postgres-to-cnpg.sh
	KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/migrate-dev-postgres-to-cnpg.sh

k3s-cutover-dev-data-layer-phase3:
	@chmod +x scripts/k3s/cutover-dev-data-layer-phase3.sh scripts/k3s/migrate-dev-postgres-to-cnpg.sh scripts/k3s/verify-data-layer-phase3-dev.sh scripts/k3s/verify-data-layer-phase2-stg.sh scripts/sync_dev_overlay_config.sh
	KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/cutover-dev-data-layer-phase3.sh

k3s-verify-data-layer-phase3-dev:
	@chmod +x scripts/k3s/verify-data-layer-phase3-dev.sh
	KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/verify-data-layer-phase3-dev.sh

# Data layer phase ⑤ — PROD cutover: legacy .80 → CNPG bifrost_prod
k3s-migrate-prod-postgres-to-cnpg:
	@chmod +x scripts/k3s/migrate-prod-postgres-to-cnpg.sh
	KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/migrate-prod-postgres-to-cnpg.sh

# Final legacy .80 archive + first dev/stg baseline from CNPG prod
k3s-backup-legacy-postgres-final:
	@chmod +x scripts/k3s/backup-legacy-postgres-final.sh
	KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/backup-legacy-postgres-final.sh

k3s-clone-cnpg-prod-to-dev-stg:
	@chmod +x scripts/k3s/clone-cnpg-prod-to-dev-stg.sh scripts/k3s/fix-cnpg-db-ownership.sh
	KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/clone-cnpg-prod-to-dev-stg.sh

k3s-fix-cnpg-db-ownership:
	@chmod +x scripts/k3s/fix-cnpg-db-ownership.sh
	KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/fix-cnpg-db-ownership.sh $(DBS)

k3s-cutover-prod-data-layer-phase4:
	@chmod +x scripts/k3s/cutover-prod-data-layer-phase4.sh scripts/k3s/migrate-prod-postgres-to-cnpg.sh scripts/k3s/verify-data-layer-phase4-prod.sh scripts/k3s/verify-data-layer-phase3-dev.sh scripts/sync_prod_overlay_config.sh
	KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/cutover-prod-data-layer-phase4.sh

k3s-verify-data-layer-phase4-prod:
	@chmod +x scripts/k3s/verify-data-layer-phase4-prod.sh
	KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/verify-data-layer-phase4-prod.sh

# Data layer phase ⑥ — Redis live/queue @ data NS
k3s-install-data-layer-phase5-redis:
	@chmod +x scripts/k3s/install-data-layer-phase5-redis.sh
	KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/install-data-layer-phase5-redis.sh

k3s-verify-data-layer-phase5-data:
	@chmod +x scripts/k3s/verify-data-layer-phase5-data.sh
	KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/verify-data-layer-phase5-data.sh

k3s-cutover-stg-data-layer-phase5-redis:
	@chmod +x scripts/k3s/cutover-stg-data-layer-phase5-redis.sh scripts/k3s/verify-data-layer-phase5-stg.sh scripts/k3s/verify-data-layer-phase5-data.sh
	KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/cutover-stg-data-layer-phase5-redis.sh

k3s-verify-data-layer-phase5-stg:
	@chmod +x scripts/k3s/verify-data-layer-phase5-stg.sh
	KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/verify-data-layer-phase5-stg.sh

k3s-cutover-dev-data-layer-phase5-redis:
	@chmod +x scripts/k3s/cutover-dev-data-layer-phase5-redis.sh scripts/k3s/verify-data-layer-phase5-dev.sh scripts/k3s/verify-data-layer-phase5-data.sh scripts/sync_dev_overlay_config.sh
	KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/cutover-dev-data-layer-phase5-redis.sh

k3s-verify-data-layer-phase5-dev:
	@chmod +x scripts/k3s/verify-data-layer-phase5-dev.sh
	KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/verify-data-layer-phase5-dev.sh

k3s-cutover-prod-data-layer-phase5-redis:
	@chmod +x scripts/k3s/cutover-prod-data-layer-phase5-redis.sh scripts/k3s/verify-data-layer-phase5-prod.sh scripts/k3s/verify-data-layer-phase5-data.sh scripts/sync_prod_overlay_config.sh
	KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/cutover-prod-data-layer-phase5-redis.sh

k3s-verify-data-layer-phase5-prod:
	@chmod +x scripts/k3s/verify-data-layer-phase5-prod.sh
	KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/verify-data-layer-phase5-prod.sh

# P1 — minimal Argo CD in cicd (Session S1; verify Ops Console → Delivery → GitOps probe)
k3s-install-argocd:
	@chmod +x scripts/k3s/install-argocd.sh
	KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/install-argocd.sh

k3s-verify-argocd:
	@kubectl --kubeconfig $(KUBECONFIG) get deploy argocd-server -n cicd
	@kubectl --kubeconfig $(KUBECONFIG) get applications.argoproj.io -n cicd

# P3 — Gitea + Registry + Tekton + smoke Pipeline (Session S3; verify Ops Console → Delivery)
k3s-install-cicd-stack:
	@chmod +x scripts/k3s/install-cicd-stack.sh
	KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/install-cicd-stack.sh

k3s-verify-cicd-stack:
	@kubectl --kubeconfig $(KUBECONFIG) get deploy registry gitea -n cicd
	@kubectl --kubeconfig $(KUBECONFIG) get deploy tekton-pipelines-controller -n tekton-pipelines
	@kubectl --kubeconfig $(KUBECONFIG) get pipeline bifrost-smoke -n cicd

# P4 — stg smoke images + k8s/overlays/stg + Argo Application bifrost-stg (Session S4)
k3s-install-bifrost-stg:
	@chmod +x scripts/k3s/install-bifrost-stg.sh
	KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/install-bifrost-stg.sh

k3s-verify-bifrost-stg:
	@kubectl --kubeconfig $(KUBECONFIG) get application bifrost-stg -n cicd
	@kubectl --kubeconfig $(KUBECONFIG) get deploy,pods -n bifrost-stg
	@kubectl --kubeconfig $(KUBECONFIG) get pipeline bifrost-build-stg -n cicd

# S7 — Gitea primary Git + Tekton clone smoke (bifrost-trade-frontend mirror)
# S7.5 — Gitea PVC + NodePort (repos survive pod restart)
k3s-install-gitea-persistent:
	@chmod +x scripts/k3s/install-gitea-persistent.sh
	KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/install-gitea-persistent.sh

k3s-bootstrap-gitea-mirrors:
	@chmod +x scripts/k3s/bootstrap-gitea-mirrors.sh
	KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/bootstrap-gitea-mirrors.sh

k3s-install-ci-frontend-git:
	@chmod +x scripts/k3s/install-ci-frontend-git.sh scripts/k3s/bootstrap-gitea-mirrors.sh scripts/k3s/install-gitea-persistent.sh
	KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/install-ci-frontend-git.sh

k3s-verify-ci-frontend-git:
	@kubectl --kubeconfig $(KUBECONFIG) get pvc gitea-data -n cicd
	@kubectl --kubeconfig $(KUBECONFIG) get pipeline bifrost-clone-frontend-smoke -n cicd
	@kubectl --kubeconfig $(KUBECONFIG) get task bifrost-git-clone-gitea -n cicd
	@kubectl --kubeconfig $(KUBECONFIG) get secret gitea-git-credentials -n cicd

# S8 — real frontend Kaniko build from Gitea (bifrost-trade-frontend + bifrost-ui)
k3s-install-ci-frontend-build:
	@chmod +x scripts/k3s/install-ci-frontend-build.sh scripts/k3s/bootstrap-gitea-mirrors.sh
	KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/install-ci-frontend-build.sh

k3s-verify-ci-frontend-build:
	@kubectl --kubeconfig $(KUBECONFIG) get pipeline bifrost-build-frontend-stg -n cicd
	@kubectl --kubeconfig $(KUBECONFIG) get task bifrost-kaniko-frontend-real -n cicd
	@kubectl --kubeconfig $(KUBECONFIG) get configmap bifrost-frontend-stg-dockerfile -n cicd
	@curl -sf http://192.168.10.73:30500/v2/bifrost-frontend/tags/list || echo "registry tag check skipped"

# S9 / Phase B — deliver-stg (9 APIs + frontend + nginx gateway)
k3s-install-ci-deliver-stg:
	@chmod +x scripts/k3s/install-phase-b-stg.sh
	KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/install-phase-b-stg.sh

k3s-verify-ci-deliver-stg:
	@kubectl --kubeconfig $(KUBECONFIG) get pipeline bifrost-deliver-stg -n cicd
	@kubectl --kubeconfig $(KUBECONFIG) get task bifrost-kaniko-all-apis-stg -n cicd
	@curl -sf -o /dev/null -w "stg-gateway HTTP %{http_code}\n" http://192.168.10.73:30880/
	@curl -sf -o /dev/null -w "stg-monitor HTTP %{http_code}\n" http://192.168.10.73:30880/api/monitor/status

# Phase B — stg v2 full stack (PG/Redis/nginx/9 APIs/frontend/worker/socket; Live TWS + Massive)
k3s-install-phase-b-stg:
	@chmod +x scripts/k3s/install-phase-b-stg.sh scripts/sync_stg_config.sh
	KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/install-phase-b-stg.sh

k3s-verify-phase-b-stg:
	@kubectl --kubeconfig $(KUBECONFIG) get deploy -n bifrost-stg
	@kubectl --kubeconfig $(KUBECONFIG) get svc nginx -n bifrost-stg
	@curl -sf -o /dev/null -w "gateway %{http_code}\n" http://192.168.10.73:30880/
	@curl -sf -o /dev/null -w "monitor %{http_code}\n" http://192.168.10.73:30880/api/monitor/status

k3s-verify-phase-b-stg-v2:
	@chmod +x scripts/k3s/verify-phase-b-stg-v2.sh
	KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/verify-phase-b-stg-v2.sh

k3s-verify-w11-trade-k8s-native:
	@chmod +x scripts/k3s/verify-w11-trade-k8s-native.sh
	KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/verify-w11-trade-k8s-native.sh

k3s-verify-placement:
	@chmod +x scripts/k3s/verify-placement-governance.sh
	KUBECONFIG=$(KUBECONFIG) PLATFORM_API=$(PLATFORM_API) ./scripts/k3s/verify-placement-governance.sh

sync-stg-config:
	@chmod +x scripts/sync_stg_config.sh
	./scripts/sync_stg_config.sh

# Sync Gitea mirrors from GitHub (Tekton clones Gitea, not local workspace)
k3s-sync-gitea-mirrors:
	@chmod +x scripts/k3s/bootstrap-gitea-mirrors.sh
	KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/bootstrap-gitea-mirrors.sh

# Rebuild stg images (9 APIs + frontend + worker + socket) and rollout bifrost-stg
k3s-deliver-stg:
	@chmod +x scripts/k3s/run-deliver-stg.sh scripts/k3s/bootstrap-gitea-mirrors.sh scripts/sync_stg_config.sh
	KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/run-deliver-stg.sh

k3s-deliver-prod:
	@chmod +x scripts/k3s/run-deliver-prod.sh scripts/k3s/bootstrap-gitea-mirrors.sh scripts/sync_prod_k8s_config.sh
	KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/run-deliver-prod.sh

sync-platform-k8s-config:
	@chmod +x scripts/sync_platform_k8s_config.sh
	./scripts/sync_platform_k8s_config.sh

k3s-deliver-platform:
	@chmod +x scripts/k3s/run-deliver-platform.sh scripts/k3s/bootstrap-gitea-mirrors.sh scripts/sync_platform_k8s_config.sh
	KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/run-deliver-platform.sh

k3s-install-platform-stg:
	@chmod +x scripts/sync_platform_k8s_config.sh
	./scripts/sync_platform_k8s_config.sh
	kubectl --kubeconfig $(KUBECONFIG) create namespace bifrost-platform-stg --dry-run=client -o yaml | kubectl --kubeconfig $(KUBECONFIG) apply -f -
	kubectl --kubeconfig $(KUBECONFIG) apply -k k8s/overlays/platform-stg
	kubectl --kubeconfig $(KUBECONFIG) apply -f k8s/cicd/applications/bifrost-platform-stg.yaml
	kubectl --kubeconfig $(KUBECONFIG) apply -f k8s/cicd/tekton/rbac-deliver-platform.yaml

k3s-verify-phase-b-prod:
	@chmod +x scripts/k3s/verify-phase-b-prod.sh
	KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/verify-phase-b-prod.sh

k3s-verify-p3-prod-cutover:
	@chmod +x scripts/k3s/verify-p3-prod-cutover.sh
	KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/verify-p3-prod-cutover.sh

k3s-install-ci-deliver-prod:
	@chmod +x scripts/k3s/run-deliver-prod.sh
	kubectl --kubeconfig $(KUBECONFIG) apply -f k8s/cicd/tekton/task-verify-prod-deliver.yaml
	kubectl --kubeconfig $(KUBECONFIG) apply -f k8s/cicd/tekton/rbac-deliver-prod.yaml
	kubectl --kubeconfig $(KUBECONFIG) apply -f k8s/cicd/tekton/pipeline-deliver-prod.yaml
	kubectl --kubeconfig $(KUBECONFIG) apply -f k8s/cicd/applications/bifrost-prod.yaml

k3s-configure-registry:
	@chmod +x scripts/k3s/configure-insecure-registry.sh
	@echo "On each K3s node: sudo bash scripts/k3s/configure-insecure-registry.sh"
	@echo "Or remote: K3S_SSH_HOSTS=\"user@host ...\" ./scripts/k3s/configure-insecure-registry.sh"

# One-time agent join — set K3S_JOIN_HOST=user@gpu-server and K3S_TOKEN on target
K3S_JOIN_HOST ?=
K3S_URL ?= https://$(K3S_NODE_IP):6443

k3s-join-agent-remote:
	@test -n "$(K3S_JOIN_HOST)" || (echo "Set K3S_JOIN_HOST=user@host" >&2; exit 1)
	@chmod +x scripts/k3s/install-agent.sh
	scp scripts/k3s/install-agent.sh $(K3S_JOIN_HOST):~/install-k3s-agent.sh
	@echo "On target (interactive sudo):"
	@echo "  ssh -t $(K3S_JOIN_HOST) 'sudo K3S_URL=$(K3S_URL) K3S_TOKEN=<token> K3S_NODE_IP=<lan-ip> bash ~/install-k3s-agent.sh'"

# P5a — 4090 gpu-server @ 192.168.10.60 (warehouse + compute + GPU)
K3S_GPU_HOST ?= vision@192.168.10.60
K3S_GPU_NODE_IP ?= 192.168.10.60
K3S_BOOTSTRAP_HOST ?= vision@192.168.10.73

k3s-join-gpu-server:
	@chmod +x scripts/k3s/join-gpu-server.sh scripts/k3s/label-gpu-server.sh scripts/k3s/fetch-join-token.sh scripts/k3s/install-agent.sh scripts/k3s/configure-insecure-registry.sh
	GPU_HOST=$(K3S_GPU_HOST) K3S_NODE_IP=$(K3S_GPU_NODE_IP) BOOTSTRAP_HOST=$(K3S_BOOTSTRAP_HOST) KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/join-gpu-server.sh

# ubt-k3s-04 @ 192.168.10.75 — general K3s agent
K3S_UBT04_HOST ?= vision@192.168.10.75
K3S_UBT04_NODE_IP ?= 192.168.10.75

k3s-join-ubt-k3s-04:
	@chmod +x scripts/k3s/join-ubt-k3s-04.sh scripts/k3s/fetch-join-token.sh scripts/k3s/install-agent.sh scripts/k3s/configure-insecure-registry.sh
	AGENT_HOST=$(K3S_UBT04_HOST) K3S_NODE_IP=$(K3S_UBT04_NODE_IP) BOOTSTRAP_HOST=$(K3S_BOOTSTRAP_HOST) KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/join-ubt-k3s-04.sh

# ubt-k3s-05 @ 192.168.10.77 — general K3s agent
K3S_UBT05_HOST ?= vision@192.168.10.77
K3S_UBT05_NODE_IP ?= 192.168.10.77

k3s-join-ubt-k3s-05:
	@chmod +x scripts/k3s/join-ubt-k3s-05.sh scripts/k3s/fetch-join-token.sh scripts/k3s/install-agent.sh scripts/k3s/configure-insecure-registry.sh
	AGENT_HOST=$(K3S_UBT05_HOST) K3S_NODE_IP=$(K3S_UBT05_NODE_IP) BOOTSTRAP_HOST=$(K3S_BOOTSTRAP_HOST) KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/join-ubt-k3s-05.sh

# ubt-k3s-06 @ 192.168.10.79 — general K3s agent (reinstalled former PG .80 box)
K3S_UBT06_HOST ?= vision@192.168.10.79
K3S_UBT06_NODE_IP ?= 192.168.10.79

k3s-join-ubt-k3s-06:
	@chmod +x scripts/k3s/join-ubt-k3s-06.sh scripts/k3s/fetch-join-token.sh scripts/k3s/install-agent.sh scripts/k3s/configure-insecure-registry.sh
	AGENT_HOST=$(K3S_UBT06_HOST) K3S_NODE_IP=$(K3S_UBT06_NODE_IP) BOOTSTRAP_HOST=$(K3S_BOOTSTRAP_HOST) KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/join-ubt-k3s-06.sh

k3s-fetch-join-token:
	@chmod +x scripts/k3s/fetch-join-token.sh
	BOOTSTRAP_HOST=$(K3S_BOOTSTRAP_HOST) ./scripts/k3s/fetch-join-token.sh

k3s-label-gpu-server:
	@chmod +x scripts/k3s/label-gpu-server.sh
	KUBECONFIG=$(KUBECONFIG) GPU_NODE_NAME=gpu-server ./scripts/k3s/label-gpu-server.sh

# Step 2 — compute workloads on gpu-server (Ollama + MinIO, scale-to-zero)
gpu-install-compute-stack:
	@chmod +x scripts/k3s/install-compute-stack.sh scripts/k3s/gpu-workload.sh
	KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/install-compute-stack.sh

gpu-workloads-status:
	@chmod +x scripts/k3s/gpu-workload.sh
	KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/gpu-workload.sh status

gpu-ollama-up:
	@chmod +x scripts/k3s/gpu-workload.sh
	KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/gpu-workload.sh ollama-up

gpu-ollama-down:
	@chmod +x scripts/k3s/gpu-workload.sh
	KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/gpu-workload.sh ollama-down

gpu-warehouse-up:
	@chmod +x scripts/k3s/gpu-workload.sh
	KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/gpu-workload.sh warehouse-up

gpu-warehouse-down:
	@chmod +x scripts/k3s/gpu-workload.sh
	KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/gpu-workload.sh warehouse-down

gpu-workloads-up:
	@chmod +x scripts/k3s/gpu-workload.sh
	KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/gpu-workload.sh all-up

gpu-workloads-down:
	@chmod +x scripts/k3s/gpu-workload.sh
	KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/gpu-workload.sh all-down

# Step 3 — WOL wake + idle poweroff (runs on bootstrap by default)
gpu-power-manager:
	@chmod +x scripts/k3s/gpu-node-power-manager.sh
	GPU_POWER_ENV=$(CURDIR)/config/gpu-node-power.env KUBECONFIG=$(KUBECONFIG) ./scripts/k3s/gpu-node-power-manager.sh

gpu-install-power-manager:
	@chmod +x scripts/k3s/install-gpu-power-manager.sh scripts/k3s/install-gpu-power-manager-remote.sh
	@test -f config/gpu-node-power.env || cp config/gpu-node-power.env.example config/gpu-node-power.env
	GPU_POWER_ENV=$(CURDIR)/config/gpu-node-power.env ./scripts/k3s/install-gpu-power-manager.sh

# ── Cleanup ───────────────────────────────────────────────────────────────────

# WARNING: prune removes Docker builder cache — avoid during active 2C signoff rebuild loops.
clean:
	$(COMPOSE) down -v --remove-orphans
	docker system prune -f
