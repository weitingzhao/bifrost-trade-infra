# Bifrost Trade — Infrastructure Handbook

Deployment center for the `bifrost-trade-*` monorepo: Docker Compose today, K3s target tomorrow.

## Quick commands

```bash
cd bifrost-trade-infra
cp .env.example .env          # first time
make prod-preflight-local     # full local prod smoke
make prod-health              # 9 API + PG + Redis via nginx
make dev                      # dev compose (hot reload)
```

## Documentation map

| Topic | Document |
|-------|----------|
| **Next build target** | Ops Console → Architecture → Blueprint § AI Native Platform (`blueprintCatalog.ts`) |
| **Platform Console** | [bifrost-platform](../../bifrost-platform) — `:5180` matrix UI · API `:8780` |
| **Where we are going** | Ops Console → **Architecture → Platform Roadmap** (`roadmapCatalog.ts`) |
| **K3s target design** | Ops Console → **Architecture → K3s Architecture** (`k3sArchitectureCatalog.ts`) |
| **K3s bootstrap** | Ops Console → **Architecture → K3s Bootstrap** (`k3sBootstrapCatalog.ts`) |
| **Deploy mainline** | Ops Console → **Program → Deploy Mainline** (`deployMainlineCatalog.ts`) |
| **Migration status** | [Migration Tracking](MIGRATION_TRACKING.md) |
| **2C-A sign-off** | [Phase 2C Sign-off Master](PHASE2C_SIGNOFF_MASTER.md) |
| **Docker rebuild** | [Docker Build](DOCKER_BUILD.md) |

## MkDocs

```bash
pip install -r requirements-docs.txt
./scripts/start_docs.sh                 # http://127.0.0.1:8050
# or: make docs

Platform control-plane docs: [bifrost-platform](../../bifrost-platform) → `./scripts/start_docs.sh` → http://127.0.0.1:8060
```

## Service ports (via nginx)

| Service | Path / port |
|---------|-------------|
| Frontend | `http://localhost/` |
| Monitor API | `/api/monitor/` → 8765 |
| … | See `CLAUDE.md` in repo root |
