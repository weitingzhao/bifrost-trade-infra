# Phase 2C — Linux 生产栈签字（M7）

**前置**： [PHASE2B_SIGNOFF_MASTER.md](../../bifrost-trade-frontend/docs/PHASE2B_SIGNOFF_MASTER.md) Final sign-off 完成。

**分两阶段**（Owner 选定 2026-06-04）：

| 阶段 | 目标 | 状态 |
|------|------|------|
| **2C-A** | `docker-compose.yml` 对齐 monorepo + 本地/staging 冒烟 | Agent 实施中 |
| **2C-B** | 192.168.10.70 生产切换 + Owner 签字 | 排期 |

---

## 2C-A — Compose 冒烟（Mac / staging）

### 命令

```bash
cd bifrost-trade-infra
cp .env.example .env   # 首次：填 GITHUB_ORG、POSTGRES_PASSWORD、POLYGON_API_KEY
make prod-preflight      # sync-prod-config + build + up + prod-health
# 可选隔离空库：make prod-embedded-infra
```

### Agent 机械门禁

| Check | Pass | Date | Remarks |
|-------|------|------|---------|
| `docker compose config` 无 ib-edge/data/research/engine | [ ] | | |
| `make prod-build` 在当前 monorepo 可构建 | [ ] | | 需 `GITHUB_ORG` + git refs |
| `make prod-health` 9 API via nginx + PG/Redis | [ ] | | IB 离线时 monitor degraded 可备注 |
| 前端 `npm run build`（production + `.env.production`） | [ ] | | |
| 浏览器 `http://localhost/` 关键路由 | [ ] | | live / celery / settings/api |

### Owner 2C-A（可选）

| Route | Business checks | Pass | Owner date | Remarks |
|-------|-----------------|------|------------|---------|
| `/` SPA | Loads via nginx | [ ] | | |
| `/market/live` | Quotes + SSE | [ ] | | 需 ingestor |
| `/operations/celery` | 8 tables | [ ] | | |
| `/settings/api` | 5 tabs health | [ ] | | |

---

## 2C-B — 192.168.10.70 生产切换 Runbook

**维护窗口前置**：

1. Prod DB 备份（`192.168.10.80` / `bifrost_prod` 或现网库名）
2. 确认 **R-DV3**：停 Legacy `run_engine.py`，仅 New `daemon` 自动下单
3. 通知：Legacy UI `http://192.168.10.70/` 将切换

### 切换步骤

```bash
# 在 192.168.10.70（Linux 服务器）
cd bifrost-trade-infra
git pull   # 各 bifrost-trade-* repo 同步 tag/ref

# 1) 停 Legacy（systemd / 手工 — 保持 bifrost-trader-engine 只读）
#    - run_engine.py
#    - Legacy 多端口 API (8711–8741)
#    - Legacy frontend

# 2) 配置
cp .env.example .env
# 填写：GITHUB_ORG, BIFROST_*_REF, POSTGRES_*, REDIS_*, IB_*, POLYGON_API_KEY
# POSTGRES_DB=bifrost_prod（或现网库名）
# BIFROST_ENV=prod

make sync-prod-config
make prod-preflight
make prod-health
```

### Owner 生产签字

| Check | Pass | Owner date | Remarks |
|-------|------|------------|---------|
| `make prod-health` 9/9 via nginx | [ ] | | |
| Global strip + Live SSE | [ ] | | TWS + ingestor |
| Daemon control `/operations/daemon` | [ ] | | |
| Celery + Socket pages | [ ] | | |
| 与 Legacy 并排关键路由等价（切换前截图对照） | [ ] | | |

### 回滚

```bash
docker compose down
# 恢复 Legacy engine + API + frontend（不改 Legacy .env）
```

---

## 架构对照（已实施）

| 项 | Legacy prod | New prod（Phase 2C） |
|----|-------------|----------------------|
| Daemon | `engine` / `run_engine.py` | `daemon` / `run_daemon.py` |
| IB | `bifrost-trade-ib-edge` | `bifrost-trade-socket` |
| Celery | `bifrost-trade-data` | `bifrost-trade-worker` |
| Research worker | 独立容器 | 并入 `api-research` |
| PG/Redis | compose 内嵌（旧） | **外置 LAN**（`embedded-infra` profile 可选） |
| 前端 API | Legacy 多端口 | nginx 同源 `/api/{domain}/` |
| 入口 | nginx :80 | nginx :80（frontend 无 host 端口映射） |

---

## Final sign-off — Phase 2C CLOSED

- [ ] 2C-A Agent 机械门禁全 Pass
- [ ] 2C-B Owner 生产签字
- [ ] `MIGRATION_TRACKING.md` §12 Prod deployed
- [ ] 解锁 [Phase 3 — Legacy 退役](./PHASE2C_PROD_DEFERRED.md#phase-3--legacy-退役未开始)

**Status**: Phase 2C **WIP** — 2C-A compose 已对齐；待 `make prod-preflight` 冒烟与 2C-B 排期。
