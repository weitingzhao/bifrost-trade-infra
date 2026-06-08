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
| **Next build target** | [AI Native Ops Platform](../Goal/AI_NATIVE_OPS_PLATFORM.md) — 自发现/自维护/自修复发布运维 |
| **Platform Console** | [bifrost-platform](../../bifrost-platform) — `:5180` matrix UI · API `:8780` |
| **Where we are going** | [Platform Roadmap](PLATFORM_ROADMAP.md) — hardware + 2C-B + K3s phases |
| **K3s target design** | [K3s Platform Architecture](K3S_PLATFORM_ARCHITECTURE.md) |
| **Migration status** | [Migration Tracking](MIGRATION_TRACKING.md) |
| **Local Prod Final** | [Local Prod Final Signoff](LOCAL_PROD_FINAL_SIGNOFF.md) — 进行中 |
| **2C-A sign-off** | [Phase 2C Sign-off Master](PHASE2C_SIGNOFF_MASTER.md) |
| **Docker rebuild** | [Docker Build](DOCKER_BUILD.md) |

## MkDocs

```bash
pip install -r requirements-docs.txt
python scripts/run_mkdocs.py          # http://127.0.0.1:8000
# or: make docs
```

## Service ports (via nginx)

| Service | Path / port |
|---------|-------------|
| Frontend | `http://localhost/` |
| Monitor API | `/api/monitor/` → 8765 |
| … | See `CLAUDE.md` in repo root |
