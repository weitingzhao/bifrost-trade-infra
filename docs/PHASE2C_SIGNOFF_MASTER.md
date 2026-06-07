# Phase 2C — Linux 生产栈签字（M7）

**前置**： [PHASE2B_SIGNOFF_MASTER.md](../../bifrost-trade-frontend/docs/PHASE2B_SIGNOFF_MASTER.md) Final sign-off 完成。

**分两阶段**（Owner 选定 2026-06-04）：

| 阶段 | 目标 | 状态 |
|------|------|------|
| **2C-A** | `docker-compose.yml` 对齐 monorepo + 本地/staging 冒烟 | Session 0 已签；**1–9 冻结** |
| **2C-A.1** | Docker 控制面（Ops executor + Daemon/Socket UI） | **进行中** — [任务清单](./PHASE2C_A1_DOCKER_CONTROL_PLANE.md) |
| **2C-B** | 新 Docker Prod 集群上线 + Owner 签字 | 排期（**非** 70 迁移） |

---

## ⚠️ Owner 签字冻结（2026-06-06）

**Session 1–9 暂停勾选**，直至 **2C-A.1** Agent 门禁 `make verify-2c-a1` 通过（允许 SKIP 仅存在于 WP 未落地阶段；最终解冻前须全绿）。

| 已签 | 冻结 | 2C-A.1 后重验 |
|------|------|----------------|
| Session 0 | Session 1–9 | 0（复验）、1、8 必重签；2 视 IB 环境；3–7 抽样 |

**原因**：Daemon / Socket 页 Ops 表面向 systemd/同机 subprocess，与 compose 多容器未来 prod 不一致；现 Sign off 将导致 Session 8 与运维 UI 重复 QA。

---

## 2C-A — Compose 冒烟（Mac / staging）

### 命令

```bash
cd bifrost-trade-infra
cp .env.example .env   # 首次：POSTGRES_PASSWORD、POLYGON_API_KEY；本地冒烟设 BIFROST_BUILD_LOCAL=1
make prod-preflight      # 无 GITHUB_ORG 时自动 local monorepo build
# 或显式：make prod-preflight-local
# 未来新 Prod 集群（git pip）：填 GITHUB_ORG，BIFROST_BUILD_LOCAL=0
# 可选隔离空库：make prod-embedded-infra
```

**何时 rebuild**（详见 [DOCKER_BUILD.md](./DOCKER_BUILD.md)）：

| 场景 | 命令 |
|------|------|
| 日常改 Python 代码 | `make dev`（不 rebuild） |
| 栈已跑，只验门禁 | `make prod-health` |
| 仅配置变更 | `make prod-up-local` |
| pyproject / Dockerfile 变更 | `make prod-base-local` + `make prod-build-local` |
| 仅 API 代码（prod 形态） | `make prod-rebuild-local-api` |
| 全栈签验收 | `make prod-preflight-local` |

避免重构期习惯性 `make clean`（会 `docker system prune`，清掉 builder cache）。

**不碰 Legacy Prod（192.168.10.70）** — 仅浏览器只读对照；全部 Session 在 `http://localhost/` 验收。

### 2C-A Session 追踪（Owner 逐会话签字）

| Session | 范围 | Owner UI | Owner date | 备注 |
|---------|------|----------|------------|------|
| **0** | 栈门禁：`prod-health`、SPA、`/settings/api` 五 Tab、Network `/api/*` | **已签** | 2026-06-06 | Dev/Prod Health 双列全红为已知缺口，不阻塞 |
| **1** | Monitor：Global strip、侧栏灯、`/operations/daemon`、`/strategy/allocations` | **冻结** | | 待 2C-A.1；Ops 表须 docker 可信 |
| **2** | Market：`/market/live` SSE + category groups | **冻结** | | 需 ingestor / 行情 |
| **3** | Portfolio：accounts / positions / performance | **冻结** | | |
| **4** | Ledger：`/portfolio/ledger` | **冻结** | | |
| **5** | Strategy：instances / structures / opportunities / gates | **冻结** | | |
| **6** | Research：screener / discovery / greeks / SEPA | **冻结** | | |
| **7** | Massive：coverage / feed | **冻结** | | |
| **8** | Ops：celery 8 表 + socket ingest 状态 | **冻结** | | 强依赖 2C-A.1 |
| **9** | 关账：2C-A Final + `make prod-health` 复验 | **冻结** | | |

### Agent 机械门禁

| Check | Pass | Date | Remarks |
|-------|------|------|---------|
| `docker compose config` 无 ib-edge/data/research/engine | [x] | 2026-06-04 | |
| `make prod-build` / local monorepo 可构建 | [x] | 2026-06-06 | `BIFROST_BUILD_LOCAL=1` 或自动 fallback；git pip 留待未来集群 |
| `make prod-health` 9 API via nginx + PG/Redis | [x] | 2026-06-06 | nginx.conf SSE 路由已修 |
| 前端 `npm run build`（production + `.env.production`） | [x] | 2026-06-04 | bundle 含 `/api/monitor` 等同源路径 |
| `docker compose build frontend` | [x] | 2026-06-06 | lockfile 需含 Linux optional deps；`npm run sync:docker-lock` |
| Session 0 浏览器 `http://localhost/` | [x] | 2026-06-06 | Owner 已签 |

### Owner 2C-A — Session 0（已签）

| Route | Business checks | Pass | Owner date | Remarks |
|-------|-----------------|------|------------|---------|
| `/` SPA | Loads via nginx | [x] | 2026-06-06 | |
| `/settings/api` | 5 tabs health（非 Dev/Prod 双列） | [x] | 2026-06-06 | Network 走 `/api/*` |

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
| Ops 启停 | systemd / Mac subprocess | **2C-A.1** → `executor_mode: docker` |

---

## 2C-A.1 — Docker 控制面（阻塞项）

**权威任务清单**：[PHASE2C_A1_DOCKER_CONTROL_PLANE.md](./PHASE2C_A1_DOCKER_CONTROL_PLANE.md)

```bash
# 本地验收（独立 Redis，避免与 Legacy .70 抢 lease）
# .env: BIFROST_PROD_INFRA=embedded-infra 或 REDIS_HOST=redis
make prod-embedded-infra
make verify-2c-a1
# 可选破坏性启停复验：
VERIFY_2C_A1_CONTROL=1 make verify-2c-a1
```

| WP | 内容 | Pass |
|----|------|------|
| WP1 | api `executor_mode: docker` | [x] |
| WP2 | market-ingest API 字段 + compose 状态 | [ ] |
| WP3 | infra compose.sock + config.prod | [ ] |
| WP4 | frontend Daemon/Socket lamp | [ ] |
| WP5 | `make verify-2c-a1` | [ ] |
| WP6 | 解冻 Session 1–9 | [ ] |

---

## Final sign-off — Phase 2C CLOSED

- [ ] 2C-A + **2C-A.1** Agent 机械门禁全 Pass
- [ ] 2C-B Owner 生产签字
- [ ] `MIGRATION_TRACKING.md` §12 Prod deployed
- [ ] 解锁 [Phase 3 — Legacy 退役](./PHASE2C_PROD_DEFERRED.md#phase-3--legacy-退役未开始)

**Status**: Phase 2C **WIP** — 2C-A Session 0 已签；**Session 1–9 冻结**；**2C-A.1 Docker 控制面**进行中；2C-B 新集群排期。
