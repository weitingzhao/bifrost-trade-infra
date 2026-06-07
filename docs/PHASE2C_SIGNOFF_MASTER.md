# Phase 2C — Linux 生产栈签字（M7）

**前置**： [PHASE2B_SIGNOFF_MASTER.md](../../bifrost-trade-frontend/docs/PHASE2B_SIGNOFF_MASTER.md) Final sign-off 完成。

**分两阶段**（Owner 选定 2026-06-04）：

| 阶段 | 目标 | 状态 |
|------|------|------|
| **2C-A** | `docker-compose.yml` 对齐 monorepo + 本地/staging 冒烟 | Session 0–8 已签；**9 关账进行中** |
| **2C-A.1** | Docker 控制面（Ops executor + Daemon/Socket UI） | **Owner 已验**（Session 8）— [任务清单](./PHASE2C_A1_DOCKER_CONTROL_PLANE.md) |
| **2C-B** | 新 Docker Prod 集群上线 + Owner 签字 | 排期（**非** 70 迁移） |

---

## Owner 签字进度（2026-06-08 更新）

**2C-A.1 控制面**：`make verify-2c-a1` 已通过；Session 0–8 Owner 已签。

| 已签 | 下一项 | 待签 |
|------|--------|------|
| Session 0–8 | **Session 9**（2C-A Final） | 2C-B 生产切换（排期） |

**签字顺序建议**：6–7 抽样 → 0 复验 → 9 Final。

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
| **1** | Monitor：Global strip、侧栏灯、`/operations/daemon`、`/strategy/allocations` | **已签** | 2026-06-08 | Dev/Prod Health 双列全红已知缺口 |
| **2** | Market：`/market/live` SSE + category groups | **已签** | 2026-06-08 | Live SSE + category groups |
| **3** | Portfolio：accounts / positions / performance / model-analysis | **已签** | 2026-06-08 | 2B Domain 5 对照 |
| **4** | Ledger：`/portfolio/ledger` | **已签** | 2026-06-08 | 2B Domain 4 对照 |
| **5** | Strategy：instances / structures / opportunities / gates 等 | **已签** | 2026-06-08 | 2B Domain 6 对照 |
| **6** | Research：8 路由 + Stock Inspector | **已签** | 2026-06-08 | 2B Domain 9；stock-data Celery `financials_feed` 已修 |
| **7** | Massive：coverage / feed | **已签** | 2026-06-08 | 2B Domain 8 抽样 |
| **8** | Ops：celery 8 表 + socket ingest 状态 | **已签** | 2026-06-07 | docker executor；Worker instances；Connection 重试 |
| **9** | 关账：2C-A Final + `make prod-health` 复验 | **下一项** | | Session 0–8 完成后 |

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

### Owner 2C-A — Session 8（已签）

**入口**：`http://localhost/` · API 同源 `/api/ops/*` · 需 Ops token（operator/admin）。

| Route / check | Business checks | Pass | Owner date | Remarks |
|---------------|-----------------|------|------------|---------|
| `/operations/celery` | 8 tables、Queue Summary、Worker instances（Add all / 启停） | [x] | 2026-06-07 | docker executor；`celery-worker` 容器 |
| `/settings/socket` | Massive + IB ingest 分组表；Connection 列；Start/Stop/Force restart | [x] | 2026-06-07 | `runtime_kind=docker`；IB slot 重试倒计时 + 手动 ↻ |
| `/operations/daemon` | Daemon 状态 + Process control 与 compose 一致 | [x] | 2026-06-07 | 与 Socket 表同源 Ops API |
| 侧栏 Celery / Socket 灯 | 与页面 ingest / broker 健康 rollup 一致 | [x] | 2026-06-07 | Socket 黄灯可因单 slot down（备注即可） |

### Owner 2C-A — Session 1（已签）

**对照**：[PHASE2B_SIGNOFF_MASTER.md](../../bifrost-trade-frontend/docs/PHASE2B_SIGNOFF_MASTER.md) Domain 2（2B Session 7）。

| Route / check | Business checks | Pass | Owner date | Remarks |
|---------------|-----------------|------|------------|---------|
| Global strip | Open orders、Streams lamp、Daily %/$ | [x] | 2026-06-08 | |
| Sidebar lamp | Live / Monitor / Socket / Celery nav 健康灯 | [x] | 2026-06-08 | |
| `/operations/daemon` | FSM、Control、Recent ops；Process 表 `process_active` | [x] | 2026-06-08 | 与 Session 8 一致 |
| `/settings/api` Monitor tab | Network `/api/monitor/*` 200 | [x] | 2026-06-08 | Dev/Prod 双列端口探针全红 — 已知缺口 |
| `/strategy/allocations` | Current active strategy 来自 monitor | [x] | 2026-06-08 | |
| Shell TopNav | 窄屏（≤768px）顶栏菜单 | [x] | 2026-06-08 | |

### Owner 2C-A — Session 2（已签）

**对照**：[PHASE2B_SIGNOFF_MASTER.md](../../bifrost-trade-frontend/docs/PHASE2B_SIGNOFF_MASTER.md) Domain 3（2B Session 8）。

| Route / check | Business checks | Pass | Owner date | Remarks |
|---------------|-----------------|------|------------|---------|
| `/market/live` | Quotes 表加载、列与分组 | [x] | 2026-06-08 | |
| `/market/live` | SSE `quotes/stream` 推送（Network EventStream） | [x] | 2026-06-08 | nginx 无缓冲 |
| `/market/live` | Category groups（OPT/STK 等）筛选/分组 | [x] | 2026-06-08 | |
| Watchlist quotes | `/research/watchlist` OPT/STK 行更新（可选） | [x] | 2026-06-08 | |
| 侧栏 Market / Live 灯 | 与 ingest 健康一致 | [x] | 2026-06-08 | |

### Owner 2C-A — Session 3（已签）

**对照**：[PHASE2B_SIGNOFF_MASTER.md](../../bifrost-trade-frontend/docs/PHASE2B_SIGNOFF_MASTER.md) Domain 5（2B Session 2）。

| Route / check | Business checks | Pass | Owner date | Remarks |
|---------------|-----------------|------|------------|---------|
| `/portfolio/accounts` | KPI、tables、category modal | [x] | 2026-06-08 | |
| `/portfolio/positions` | Tabs、charts、attribution | [x] | 2026-06-08 | |
| `/portfolio/performance` | FilterBar、calendar、Equity Growth %/$ | [x] | 2026-06-08 | |
| `/portfolio/model-analysis` | Table expand、stress panel | [x] | 2026-06-08 | |

### Owner 2C-A — Session 4（已签）

**对照**：[PHASE2B_SIGNOFF_MASTER.md](../../bifrost-trade-frontend/docs/PHASE2B_SIGNOFF_MASTER.md) Domain 4（2B Session 3）。

| Route / check | Business checks | Pass | Owner date | Remarks |
|---------------|-----------------|------|------------|---------|
| `/portfolio/ledger` | Open/closed groups、展开行 | [x] | 2026-06-08 | |
| `/portfolio/ledger` | Execution link、Link stock fills | [x] | 2026-06-08 | |
| `/portfolio/ledger` | Options/Stock 列、Strategy PnL 着色 | [x] | 2026-06-08 | |

### Owner 2C-A — Session 5（已签）

**对照**：[PHASE2B_SIGNOFF_MASTER.md](../../bifrost-trade-frontend/docs/PHASE2B_SIGNOFF_MASTER.md) Domain 6（2B Session 4）。

| Route / check | Business checks | Pass | Owner date | Remarks |
|---------------|-----------------|------|------------|---------|
| `/strategy/instances` | Filters、sidebar detail、Create instance modal | [x] | 2026-06-08 | |
| `/strategy/win-rate` | Structure cards、drill to instances | [x] | 2026-06-08 | |
| `/strategy/structures` | Dual tables、SegmentControl | [x] | 2026-06-08 | |
| `/strategy/opportunities` | List、filters | [x] | 2026-06-08 | |
| `/strategy/allocations` | Table、Current active | [x] | 2026-06-08 | |
| `/strategy/gates` | Gates table、Safety sheet | [x] | 2026-06-08 | |
| `/strategy/option-category` | Templates、legs/meta dropdowns | [x] | 2026-06-08 | |

### Owner 2C-A — Session 6（已签）

**对照**：[PHASE2B_SIGNOFF_MASTER.md](../../bifrost-trade-frontend/docs/PHASE2B_SIGNOFF_MASTER.md) Domain 9（2B Session 5）。

**预检**：

```bash
cd bifrost-trade-infra
curl -s http://localhost/api/research/health | jq .
curl -s http://localhost/api/research/sepa/readiness | jq 'keys | length'
```

| Route / check | Business checks | Pass | Owner date | Remarks |
|---------------|-----------------|------|------------|---------|
| `/research/watchlist` | Watching → Sizing → Positions | [x] | 2026-06-08 | Session 2 已验 quotes |
| `/research/sepa` | Filter funnel、Readiness | [x] | 2026-06-08 | |
| `/research/stock-data` | Runbook、backfill | [x] | 2026-06-08 | `stocks_massive` worker + `financials_feed` 修 Celery |
| `/research/screener` | Option screener | [x] | 2026-06-08 | |
| `/research/discovery` | IV term、charts | [x] | 2026-06-08 | |
| `/research/greeks` | Filters + table | [x] | 2026-06-08 | |
| `/research/risk` | KPI tiles | [x] | 2026-06-08 | |
| Stock Inspector | 三处入口打开 Inspector | [x] | 2026-06-08 | watchlist / screener / discovery |

### Owner 2C-A — Session 7（已签）

**对照**：[PHASE2B_SIGNOFF_MASTER.md](../../bifrost-trade-frontend/docs/PHASE2B_SIGNOFF_MASTER.md) Domain 8（2B Session 6）。

**预检**：

```bash
cd bifrost-trade-infra
curl -s http://localhost/api/massive/health | jq .
curl -s http://localhost/api/ops/ops/queues/summary | jq '.queues | length'
```

| Route / check | Business checks | Pass | Owner date | Remarks |
|---------------|-----------------|------|------------|---------|
| `/settings/coverage/overview` | Stocks/Options 分块、job queues、Worker situation | [x] | 2026-06-08 | |
| `/settings/coverage/option` | Option coverage 表与 drill-down | [x] | 2026-06-08 | |
| `/settings/coverage/stock-ib` | Stock IB 覆盖 | [x] | 2026-06-08 | |
| `/settings/coverage/stock-massive` | Stock Massive 覆盖 | [x] | 2026-06-08 | |
| `/settings/feed/massive` | Massive feed 主路由 | [x] | 2026-06-08 | |
| `/settings/feed/massive-stock` | Stock feed / Execute | [x] | 2026-06-08 | |
| `/settings/feed/massive-option` | Option feed | [x] | 2026-06-08 | |
| Beat schedule | Coverage UI 可见 beat 条目 | [x] | 2026-06-08 | beat 未 compose 起可备注 |

### Owner 2C-A — Session 9（下一项 — 2C-A Final）

**目标**：Session 0–8 全部已签后关账 **2C-A**（本地/staging compose 冒烟）。**不等于** 2C-B 生产切换。

**机械门禁**（终端，栈需已 `up`）：

```bash
cd bifrost-trade-infra
make prod-health
make verify-2c-a1    # 可选；控制面已 Session 8 验过可快速过
curl -sf http://localhost/ >/dev/null && echo SPA ok
curl -s http://localhost/api/monitor/health | jq '.ok // .status'
```

| Check | Business / technical | Pass | Owner date | Remarks |
|-------|----------------------|------|------------|---------|
| `make prod-health` | 9 API via nginx + PG/Redis 探针 | [ ] | | |
| `http://localhost/` | SPA 经 nginx 加载 | [ ] | | |
| Session 0 复验 | `/settings/api` 五 Tab；Network 走 `/api/*` | [ ] | | Dev/Prod 双列全红 — 已知缺口 |
| Agent 机械门禁表 | 本节上文「Agent 机械门禁」全 [x] | [ ] | | Owner 确认无回归 |
| Session 1–8 | 追踪表全部 **已签** | [ ] | | 本关账项 |

**签字后**：2C-A 视为 **Owner 已验**；2C-B（新 Prod 集群 / `.70` 切换）另排期。

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
| WP2 | market-ingest API 字段 + compose 状态 | [x] |
| WP3 | infra compose.sock + config.prod | [x] |
| WP4 | frontend Daemon/Socket lamp | [x] |
| WP5 | `make verify-2c-a1` | [x] |
| WP6 | 解冻 Session 1–9 | 进行中（0–8 已签；9 关账） |

---

## Final sign-off — Phase 2C CLOSED

- [ ] 2C-A + **2C-A.1** Agent 机械门禁全 Pass
- [ ] 2C-B Owner 生产签字
- [ ] `MIGRATION_TRACKING.md` §12 Prod deployed
- [ ] 解锁 [Phase 3 — Legacy 退役](./PHASE2C_PROD_DEFERRED.md#phase-3--legacy-退役未开始)

**Status**: Phase 2C **WIP** — 2C-A Session **0–8 已签**；**Session 9（2C-A Final）下一项**；2C-B 新集群排期。
