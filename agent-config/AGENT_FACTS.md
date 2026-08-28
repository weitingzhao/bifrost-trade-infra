---
parity-id: agent-facts-v1
generated: 2026-08-27
authority: bifrost-platform/config/ops-context.yaml (spine) + 磁盘扫描
---

# AGENT_FACTS — Bifrost 工作区事实基线

> **本文件是 Cursor 与 Claude 两侧治理文档的共同事实源。**
> 任何规则文件（`.cursor/rules/*.mdc` 或 `CLAUDE.md`）在陈述"有哪些 repo / 端口 / 已退役什么"时，
> 必须与本文件一致。修改本文件需同时 bump `parity-id` 并跑 `scripts/check-agent-config-parity.sh`。
>
> **本文件不是决策源。** 决策与里程碑的权威源永远是 spine（见 §5）。

---

## 1. 三域架构

Bifrost = 三个域，边界不可跨越（spine **D13**，2026-08-21 SIGNED）。

| 域 | Repos | 数据库 | 职责 |
|----|-------|--------|------|
| **Trade (OLTP)** | `bifrost-trade-{core,socket,worker,api,frontend,infra}` | `bifrost_{dev,stg,prod}` 环境隔离 | 交易执行、持仓、实时监控 |
| **Research (OLAP)** | `bifrost-research` | `bifrost_golden_source` 单实例 | 分析、预测、回测、选股选期权 |
| **Ops (控制面)** | `bifrost-platform` + `bifrost-platform-plugin{,-market-data,-flex-query}` | 控制面状态（非业务库） | 环境治理、健康探测、部署编排、Agent |

跨域共享：`bifrost-ui`（`@bifrost/ui` 共享 React 组件库）。

### Ops 运维归属（2026-08-28 更正）

Ops Platform 的域分类法（`console/src/lib/architecture/systemDomainCatalog.ts`）此前把
Research 归为 **Subcontractors/Plugin**，导致它两边的发布能力都拿不到（Launch Plugin 只覆盖
ib-gateway / market-data；`bifrost-deliver-stg` 是 Trade 专属），因而长期靠本机手推镜像。

现已提升为**第一级域 `research`** —— 与 Satellite 平级的**第二 payload**：

| 角色 | 含义 |
|------|------|
| Rocket | 运载工具 —— Ops Platform 自身 |
| **Satellite** | **执行载荷** —— Trade |
| **Research** | **决策载荷** —— OLAP / Golden Source / Copilot |
| Subcontractors | 外围供数插件 —— 写 `raw_*`，与 Research 的数据流方向相反 |

发布链：`bifrost-deliver-research`（mirror-sync → clone → kaniko → rollout → verify → gitops-sync）。

### 两个 Payload 的发布互动（前端是共用驾驶舱）

`bifrost-trade-frontend` **不是第三个 payload**，它是两个 payload 共用的驾驶舱：
Research UI（83 页 / 16.3k 行）与 Portfolio / Strategy / Market 同处一个 SPA，
整体随 **Satellite** 链发布。

耦合是双向的：Research 页面读 Trade 数据（Watchlist / Discovery / Sizing 等 5 处），
Trade 页面经 Ask Copilot 读 Research 后端（Positions / Instances / Live 3 处），
且 Copilot 面板挂在 `AppLayout` —— **全站可用，打 Research 后端**。

因此两条发布链的**先后顺序不确定**：前端可能比 research-api 新（Satellite 先发），
也可能旧（Research 先发）。约定如下：

1. **前端整体随 Satellite 发布** —— 不给 Research UI 单独建交付链。同一 SPA 的
   两半版本不一致，比现在的耦合严重得多。
2. **Research API 只能向后兼容地演进** —— 破坏性变更走「加新字段 → 前端迁移 →
   下版删旧字段」三步，不允许一步到位。
3. **运行时契约校验** —— `src/lib/schemas/research.ts` + `lib/apiValidation.ts`，
   dev 模式告警、生产透传；全部 `.passthrough()` 使加字段不误报。
4. **Copilot 是跨载荷服务** —— 不属于任一 payload，读两边数据是设计如此。
   其契约按最高标准管（爆炸半径 = 全站）。



**双飞轮**：Flywheel A = Trade 业务面；Flywheel B = `bifrost-platform` 控制面。
硬边界 —— `bifrost-platform` 永远不了解 Greeks、IB 协议、SEPA、straddles、daemon 策略。

---

## 2. 活跃 Repo 清单（13 个）

| Repo | 包名 / 语言 | 域 | 备注 |
|------|------------|----|------|
| `bifrost-trade-core` | `bifrost_core` (py) | Trade | 纯共享库，无进程入口。config / persistence / portfolio / ib_operator / monitor |
| `bifrost-trade-socket` | `bifrost_socket` (py) | Trade | **半退役** — 见 §4 |
| `bifrost-trade-worker` | `bifrost_worker` (py) | Trade | 现仅 `daemon/`（Celery 已退役，见 §4） |
| `bifrost-trade-api` | `bifrost_api` (py) | Trade | 9 个逻辑域 → K8s 4 个 deployment，见 §3 |
| `bifrost-trade-frontend` | TypeScript / React 18 / Vite | Trade | **232 个 `.tsx` 页面**，8 个域目录：`copilot / market / operations / portfolio / research / settings / strategy` + `RouteErrorPage` |
| `bifrost-trade-infra` | DevOps（无包） | Trade | `k8s/{base,base-platform,cicd,compute,data,monitoring,overlays,plugin-flex-query,system}` |
| `bifrost-research` | `bifrost_research` (py) | Research | dbt 管线 + engines + Research API + Dagster 编排 |
| `bifrost-platform` | Go (api) + React (console) | Ops | 控制面；spine 宿主 |
| `bifrost-platform-plugin` | `bifrost_platform_plugin` (py) | Ops | IB Gateway 插件 → `redis-ib` |
| `bifrost-platform-plugin-market-data` | `bifrost_market_data` (py) | Ops | Polygon → `raw_market.*` / `ops_jobs.*` |
| `bifrost-platform-plugin-flex-query` | `bifrost_flex_query` (py) | Ops | IB Flex → `raw_broker.*` |
| `bifrost-ui` | `@bifrost/ui` (ts) | 共享 | shadcn 原语、Dense Data Table、Shell 导航 |
| `bifrost-analytics` | — | **已归档** | 见 §4 |

非 repo 目录：`Research-workspace/`（分析案例草稿）、`backups/`（PG dump）。

---

## 3. 端口表

### Trade API — 9 个逻辑域，K8s 4 个 deployment

| 逻辑域 | 包 | 端口 | K8s deployment |
|--------|----|------|----------------|
| monitor | `bifrost_api.monitor` | 8765 | **monitor**（合并 monitor + ops + docs） |
| ~~massive~~ | ~~`bifrost_api.massive`~~ | ~~8766~~ | **retired (P7)** → Market Data Plugin `:8790` |
| docs | `bifrost_api.docs_api` | 8767 | ↑ monitor |
| ops | `bifrost_api.ops` | 8768 | ↑ monitor |
| trading | `bifrost_api.trading` | 8769 | **account**（合并 trading + portfolio + strategy） |
| strategy | `bifrost_api.strategy` | 8770 | ↑ account |
| portfolio | `bifrost_api.portfolio` | 8771 | ↑ account |
| market | `bifrost_api.market` | 8772 | **market** |
| research | `bifrost_api.research` | 8773 | **research** |

`bifrost_api.account` 目录 = account 域实现。前端 API 路径保持 `/api/{domain}/`。

### 其余服务

| 服务 | 端口 | 归属 |
|------|------|------|
| platform-api | 8780 | Ops |
| platform-console (Vite) | 5180 | Ops |
| git-bridge | 8785 | Ops |
| probe-bridge (Satellite Probe) | 8786 | Ops |
| market-data plugin API | 8790 | Ops |
| flex-query plugin API | 8791 | Ops |
| Research API | 8795 | Research |
| trade-ui (Vite) | 5173 | Trade |
| prometheus-pf（kubectl port-forward） | 9090 | Ops |

---

## 4. 已退役 / 归档（**不得在任何规则或文档中作为活跃实体引用**）

| 实体 | 状态 | 依据 |
|------|------|------|
| `bifrost-trader-engine` | **已 NAS 归档并移出工作区** | spine **D8**，2026-06-29 |
| `bifrost-trade-ib-edge` | 被 `bifrost-trade-socket` 取代 | 2026-05-30 架构调整 |
| Trade Celery runtime + Celery workers + Flower `:5555` | 退役 | Wave 5（runtime）· **D-Wave-6.1**（代码）· **D-Wave-6.2**（文档/配置），2026-08-24 |
| massive API `:8766` + Polygon Massive WS | 退役 | P7 → Market Data Plugin `:8790` |
| `bifrost-analytics` | 并入 `bifrost-research/src/bifrost_research/dbt/` | spine **D13**，2026-08-21。目录保留但 README 标 ARCHIVED，**勿再改** |
| 裸机 PostgreSQL `.80` | 退役 → CloudNativePG @ `data` NS | spine **D2-prime**，2026-06-20；节点重装为 `ubt-k3s-06` |
| `features_daily` / `features_option` 等 legacy schema | DROP | **D-Wave-6.6**，2026-08-24；canonical 为 `features.*` |
| Trade `public.job_*` Celery 表 | 退役（core 0.10.6） | → `ops_jobs.job_ingest` |

### `bifrost-trade-socket` — 半退役，尚未授权删除

生产 IB 实时总线已由 **Platform IB Gateway Plugin → `redis-ib`** 承接（IBGP3/4 done）。
socket 仓库（52 py / ~10.4k 行）仍在 `docker-compose.dev.yml` 默认启动、Tekton 仍 build 镜像。
退役设计文档 `bifrost-trade-infra/docs/WAVE_14G_F_SOCKET_RETIREMENT.md` 标注
**DESIGN ONLY — 未授权实施删除 / 改 compose / 改 CI**。Owner 决策清单未走完前不得实施。

---

## 5. 权威源链（Governance priority）

顺序：**代码 → Console Governance catalogs → spine**。

| 主题 | 权威源 |
|------|--------|
| 里程碑、决策 D1–D13、D-Wave-*、north star、focus | `bifrost-platform/config/ops-context.yaml` → `GET /api/v1/context` |
| Agent 模式 · 禁止动作 · D10 冻结 | `bifrost-platform/console/src/lib/architecture/agentProtocolCatalog.ts`（`FORBIDDEN_ACTIONS`） |
| 数据库 schema | `bifrost-trade-core/docs/DATABASE.md` |
| 硬件 / 网络拓扑 | `bifrost-platform/config/topology.yaml` · `clusters.yaml` · Console Runtime Map |
| K8s workload 放置 | `console/src/lib/architecture/workloadPlacementCatalog.ts` · `GET /api/v1/cluster/placement` |
| 迁移进度 | `bifrost-trade-infra/docs/MIGRATION_TRACKING.md` |
| Golden Source 保留策略 | `bifrost-trade-infra/docs/GOLDEN_SOURCE_RETENTION.md` |

`bifrost-platform` **没有** `docs/` 目录 —— 其治理内容全在 Console catalogs 与 `config/`。

---

## 6. 运行环境（替代已退役的 run-environment 规则）

- **部署阶段**：`deployment.phase: k3s_partial`（`topology.yaml`）。不是 Docker Compose。
- **集群**：`bifrost-bootstrap`，K3s，apiserver `https://192.168.10.73:6443`
- **Namespaces**：`cicd` · `data` · `bifrost-dev` · `bifrost-stg` · `bifrost-prod` ·
  `bifrost-platform-stg` · `bifrost-platform-prod` · `monitoring` · `ai` · `data-warehouse`
  · `research` · `plugin-market-data` · `plugin-flex-query`
- **数据层**：CloudNativePG @ `data` NS；`redis-live` + `redis-queue` per env；`redis-ib` @ `data` NS（共享 IB 总线）
- **TWS**：Win11 专用机（Host + Secondary），**永不调度进 K3s**，Socket/Gateway 经 LAN 连接
- **GPU**：`gpu-server` @ 192.168.10.60（RTX 4090）— Ollama @ `ai` NS，MinIO @ `data-warehouse` NS
- **Dev 拓扑**：Mac 本地 = IDE + Vite(:5173) + 当前正在编辑的那一个 API；其余全在 K3s
- **本地 dev 服务**：`bdev` CLI + tmux session `bifrost`，声明在 `~/.bifrost-dev/sessions.yaml`

---

## 7. 当前 spine 状态（快照 — 以 `GET /api/v1/context` 为准）

- `deployment.phase`: `k3s_partial`
- `active_track`: `trade_ib_client_migration_rollout`
- `focus.headline`: `TIBM W3 signed — STG read-path complete (D10 BLOCKED)`
- `flywheel_primary`: **B**（runtime/ops）
- **D10 = BLOCKED** — 交易执行冻结，见 §8

---

## 8. D10 — 交易执行冻结（硬边界）

**状态：BLOCKED**（spine，signed 2026-07-04）。

实盘下单、daemon 自动交易扩容、S08 execution wiring 全部禁止。
解锁需要 **两个条件同时满足**：Owner 明文书面指令 **且** spine `decisions[id=D10].status` → `UNLOCKED`。

机械强制：`scripts/agent-guard/preflight.js`（Claude `PreToolUse` + Cursor `beforeShellExecution`）
运行时读 spine 的 D10 状态决定拦截与否 —— 闸门与 spine 同源，只有一个开关。

Infra guards（未解锁前不得"修复"）：

| 环境 | Guard 文件 |
|------|-----------|
| STG | `bifrost-trade-infra/k8s/overlays/stg/daemon-scale-zero.patch.yaml`（`replicas: 0`） |
| PROD | `bifrost-trade-infra/k8s/overlays/prod/daemon-observe-safe.patch.yaml`（observe 模式，模拟对冲） |

---

## 8b. MCP 工具面（Claude 侧 `.mcp.json` · Cursor 侧 `~/.cursor/mcp.json`）

源码 `bifrost-platform/mcp/`（stdio + 官方 SDK）。Claude 侧注册 6 个 server，共 133 个工具（含重叠）：

| server | focus | 工具 | 令牌角色 |
|--------|-------|------|---------|
| `bifrost-platform` | — | 85 | operator |
| `bifrost-kubernetes` | `kubernetes` | 18 | operator |
| `bifrost-redis` | `redis` | 6 | **viewer** |
| `bifrost-postgres` | `postgres` | 8 | **viewer** |
| `bifrost-prometheus` | `prometheus` | 4 | **viewer** |
| `bifrost-trade-api` | — | 12 | Trade 网关（只读） |

- **令牌分级是机械强制**：只读桥拿 viewer 角色，写路由被 platform-api 服务端 RBAC 拒绝
- focus 白名单定义在 `mcp/platform/src/focusBridges.ts`，依据 `api/internal/mcp/catalog.go` 权威目录
- 令牌走 `${PLATFORM_*_TOKEN:-<dev 默认>}` 环境变量展开，不落盘
- `mcp/unifi/` 未注册（D9 网络执行路径）
- 详见 `.mcp.json.README.md`

---

## 9. 如何刷新本文件

本文件会随项目演进过期。刷新时：

1. 读 spine `bifrost-platform/config/ops-context.yaml` 的 `deployment` / `focus` / `milestones` / `decisions`
2. 读 `agentProtocolCatalog.ts` 的 `FORBIDDEN_ACTIONS` 与 `AGENT_MODES`
3. 磁盘扫描核对 repo 清单、端口、页面数
4. bump `parity-id`（`agent-facts-v<n+1>`）+ 更新 `generated:`
5. 跑 `bash scripts/check-agent-config-parity.sh`
