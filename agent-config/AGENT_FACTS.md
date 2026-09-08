---
parity-id: agent-facts-v2
generated: 2026-09-06
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
| **Trade (OLTP)** | `bifrost-trade-{core,worker,api,frontend,infra}`（socket 已 Archive/移出） | `bifrost_{dev,stg,prod}` 环境隔离 | 交易执行、持仓、实时监控 |
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

## 2. 活跃 Repo 清单（12 个）

| Repo | 包名 / 语言 | 域 | 备注 |
|------|------------|----|------|
| `bifrost-trade-core` | `bifrost_core` (py) | Trade | 纯共享库，无进程入口。config / persistence / portfolio / ib_operator / monitor |
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

### L-1 带外操作面（两台 Mac mini：`.50` ops-mac-agent-02 · `.52` ops-mac-agent-01）

这些端口**不在集群里**，`lsof` 查不到就以为空闲会撞车。

| 服务 | 端口 | 主机 |
|------|------|------|
| remediation runner | 8781 | 两台 |
| Hermes gateway | 8782 | `.52` |
| operator-plane（L-1 路由 + patrol） | 8783 | 两台 |
| Hermes dashboard | 9119 | `.50` |

---

## 4. 已退役 / 归档（**不得在任何规则或文档中作为活跃实体引用**）

| 实体 | 状态 | 依据 |
|------|------|------|
| `bifrost-trader-engine` | **已 NAS 归档并移出工作区** | spine **D8**，2026-06-29 |
| `bifrost-trade-ib-edge` | 被 `bifrost-trade-socket` 取代 | 2026-05-30 架构调整 |
| `bifrost-trade-socket` | **GitHub Archived** · 已从多仓 workspace / CI/CD / Gitea 清除 | Owner 2026-08-31；GitHub `22bd9d6`；本地 tip/tag `b0a59f5`/`archived-14gf`（只读无法 push）；tarball 备份 |
| Trade Celery runtime + Celery workers + Flower `:5555` | 退役 | Wave 5（runtime）· **D-Wave-6.1**（代码）· **D-Wave-6.2**（文档/配置），2026-08-24 |
| massive API `:8766` + Polygon Massive WS | 退役 | P7 → Market Data Plugin `:8790` |
| `bifrost-analytics` | 并入 `bifrost-research/src/bifrost_research/dbt/` | spine **D13**，2026-08-21。目录保留但 README 标 ARCHIVED，**勿再改** |
| 裸机 PostgreSQL `.80` | 退役 → CloudNativePG @ `data` NS | spine **D2-prime**，2026-06-20；节点重装为 `ubt-k3s-06` |
| `features_daily` / `features_option` 等 legacy schema | DROP | **D-Wave-6.6**，2026-08-24；canonical 为 `features.*` |
| Trade `public.job_*` Celery 表 | 退役（core 0.10.6） | → `ops_jobs.job_ingest` |

### `bifrost-trade-socket` — RETIRED / workspace-removed（Wave 14G-F）

生产与 Inner Loop IB 实时总线权威路径：**Platform IB Gateway Plugin → `redis-ib`**（IBGP3/4）。
Owner **2026-08-31** 签批 D-14GF.1–6（R1）；同日 GitHub Archive + 授权移出多仓 workspace。

| Phase | 状态 |
|-------|------|
| 0–2 · 3 · 3b | ✅ 见 `docs/WAVE_14G_F_SOCKET_RETIREMENT.md` |
| GitHub Archive | ✅ `weitingzhao/bifrost-trade-socket` |
| 移出 Cursor / multi-root workspace | ✅（`bifrost-trade.code-workspace` 已去 folder；物理目录由 Owner 压缩移出） |
| 考古锚点 | GitHub last push `22bd9d6`；本地 tip `b0a59f5` + tag `archived-14gf`（GitHub 只读无法 push）；Owner tarball |

**勿启动** socket 三进程（双写=事故）。逃生舱仅在**解压回** `../bifrost-trade-socket` 后：  
`docker compose -f docker-compose.dev.yml --profile legacy-ib up`（禁止与 Plugin 并行）。

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

## 7b. 代码健康度棘轮（2026-08-31 新增）

治理覆盖此前只有运行时与流程两条腿；**代码资产**这一维在 Console 里不存在。
`SignalSourceKind` 原有 13 个取值全是运行时探测，新增第 14 个 `code_health` 补上。

| 实体 | 位置 |
|------|------|
| 采集器 | `bifrost-trade-infra/agent-config/scripts/code-health/scan.sh` |
| 基线 | 同目录 `baselines.env`（7 个指标 / 3 个 repo） |
| 存储 | `bifrost-platform/api/internal/codehealth/`（落盘 `agent/code-health/*.json`，保留 30 份） |
| 端点 | `GET /api/v1/code-health`（viewer）· `POST /api/v1/code-health/report`（operator） |
| MCP | `get_code_health` |
| UI | Console → Mission Control → **Code Health**；Observability 三条 `code_health` signal（satellite / research / rocket，均为 `evidence` + `optionalContract`） |
| Skill | `.claude/skills/code-health/` ·`.cursor/skills/code-health/`（`parity-id: code-health-v4`） |

**契约**：无数据 → `NOT OBSERVED`，链路每一层都不得显示为健康。

### CI 闸门（Wave 5 — Owner 批准 2026-08-31）

| 闸门 | 状态 |
|------|------|
| `bifrost-trade-frontend/.husky/pre-commit` | ✅ legacy-css + code-health |
| `bifrost-platform/.husky/pre-commit` | ✅ code-health（console npm prepare → husky） |
| `bifrost-research/.githooks/pre-commit` | ✅ `make install-hooks` |
| Tekton `bifrost-ci-{frontend,platform,python}` | ✅ Triggers + EventListener + Gitea push webhooks |
| python-ci CEL | ✅ 含 `bifrost-research`（code-health Task `when` 仅对该 repo 跑棘轮） |

安装：`make k3s-install-ci-triggers` + `make k3s-install-ci-webhooks`；校验 `make k3s-verify-ci-triggers`。

**闸门只拦 OVER**；贴顶（AT CEILING）合入放行，规划灯另见 Console Code Health Posture Summary。

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

## 8c. 运行时与安全事实（2026-09-06 实测核实）

> 来源：`gh` / `kubectl`（`~/.kube/bifrost-k3s.yaml`）/ `claude auto-mode` 实查。与 §6 冲突时以本节为准并回填 §6。

### 代码托管可见性

- GitHub `weitingzhao/*` 的 12 个工作区 repo **全部 PUBLIC**（含已归档的 `bifrost-trade-socket`）。
  推送即公开：任何 `.env`、Secret YAML、dump、token 进入提交就是公开泄露。
- 入库的 env 文件只有前端三个非秘密文件（`.env.development` / `.env.development.k3s` / `.env.production`）；
  Secret 清单只有 `*.example.yaml`；`agent-config/claude/settings.local.json` 已 gitignore。
- 集群内 Gitea 镜像 `gitea.cicd.svc.cluster.local:3000/bifrost/<repo>`（NodePort `.73:30300`）
  只由 deliver 流水线的 `mirror-sync` 写入，不手工 push。

### 集群与节点（K3s `bifrost-bootstrap`）

kubeconfig：`~/.kube/bifrost-k3s.yaml`（需 `KUBECONFIG=` 显式指定；默认 context `docker-desktop` 是本机 Docker Desktop，**不是**集群）。
读状态首选 MCP 只读工具。

| 节点 | IP | host-id | workload-pool | 角色 |
|------|----|---------|---------------|------|
| ubt-k3s-02 | 192.168.10.70 | mini-pc-a | prod-pool | PROD 首选节点（preferred affinity 100，required pool `[prod-pool, general]`，可漂移） |
| ubt-k3s-01 | 192.168.10.73 | mini-pc-c | — | 控制面、monitoring、Tekton；所有 NodePort 的访问地址 |
| ubt-k3s-04 | 192.168.10.75 | ubt-k3s-04 | data-primary | CloudNativePG |
| ubt-k3s-05 | 192.168.10.77 | ubt-k3s-05 | general | STG runtime、CI build |
| ubt-k3s-06 | 192.168.10.79 | ubt-k3s-06 | general | 通用 |
| gpu-server | 192.168.10.60 | gpu-server | compute | RTX 4090：Ollama（`ai`）、MinIO（`data-warehouse`）、重型 Tekton |

集群外：Win11 TWS ×2（topology `win11-host` / `win11-secondary`；`bifrost-platform-plugin/config/gateway.yaml` 模板写的是 `.30` / `.32`；永不调度进 K3s）、
Mac mini `.50` / `.52`（agent host）、NAS `.20`（归档与备份目标）、本机 MacBook（kubectl / MCP / Vite）。

### 入口与 NodePort

| 入口 | 地址 |
|------|------|
| kube-vip VIP | `192.168.10.100` → `trader.bifrost.lan` / `stg.trader.bifrost.lan` / `dev.trader.bifrost.lan` / `ops.bifrost.lan` / `stg.ops.bifrost.lan` |
| Trade 网关 | `.73:30880` PROD · `.73:30881` STG · `.73:30882` DEV（前端 DEV inner loop 的 API） |
| Ops Console / API | `.73:30876`–`30879` |
| registry / gitea / apiserver | `.73:30500` · `.73:30300` · `.73:6443` |

### 交付链（Argo CD @ `cicd`）

| Argo App | 源 | 同步策略 | 含义 |
|----------|----|----------|------|
| `bifrost-platform-stg` / `bifrost-platform-prod` | bifrost-trade-infra `main` | **automated + prune + selfHeal** | 推 infra main = 立即改 Ops STG/PROD 运行时 |
| `bifrost-research` | bifrost-research `main` | automated（无 prune / selfHeal） | 推 research main = 改 research 运行时；先镜像后 manifest（research-release skill） |
| `bifrost-stg` / `bifrost-prod` | bifrost-trade-infra `main` | 手动 | Trade 由 `bifrost-deliver-{stg,prod}` rollout，再 `gitops_sync_app` |

Tekton 流水线：`bifrost-ci-{frontend,platform,python}` · `bifrost-deliver-{stg,prod,platform,platform-prod,research}` ·
`bifrost-build-{stg,frontend-stg,market-data,flex-query,research-dagster}` · `bifrost-smoke` · `bifrost-clone-frontend-smoke`。
镜像仓库 `registry.cicd.svc.cluster.local:5000`。PROD 清单只走 git + Argo；`kubectl apply` prod overlay 会剥掉 Argo 跟踪注解。

### 数据层

- CloudNativePG `bifrost-postgres` @ `data`，2 实例，库 `bifrost_dev` / `bifrost_stg` / `bifrost_prod` + `bifrost_golden_source`；
  Barman 备份 → MinIO `minio.data.svc.cluster.local:9000` 桶 `s3://bifrost-postgres-backup/`（删改即毁 PITR）。
- 第二个 MinIO @ `data-warehouse`（gpu-server）供 Research / Golden Source 对象。
- `redis-ib` @ `data`：共享 IB 事件总线；`redis-live` / `redis-queue` 每环境一套。

### IB 接入模型（账户号不是秘密 — Owner 2026-09-06 明确）

- IB **登录只发生在两台 Win11 的 TWS 软件里**（Owner 手工登录 + 2FA）；工作区与集群里没有 IB 密码。
- 其余系统只经 **IB API socket**（TWS `tws_live` 端口；client_ids 70/71 Host、72/73 Secondary）由 Platform IB Gateway Plugin 连接 → `redis-ib`；
  Trade 服务不直连 TWS。
- 账户号 `U17123565`（Host）/ `U8829175`（Secondary）是标识符，UI、日志、文档可以出现。
  敏感的是账户**内容**（持仓、成交、P&L）与 Flex / Polygon / DeepSeek 等 API key。

### 本机敏感位置（只对 Owner 可见，不得进入任何仓库或外部服务）

`backups/bifrost_prod_pre_p9_*.dump`（PROD 全量 dump）· 各 repo 未跟踪 `.env`（platform、research、plugin ×3、infra、frontend `.env.development.local`）·
未跟踪 Secret YAML（`k8s/base/secrets`、`k8s/data/secrets`、`k8s/cicd/gitea/secret.yaml`、`k8s/overlays/*/…token*.yaml`）·
`~/.kube/bifrost-k3s.yaml` · `~/.bifrost-dev/`。

### Claude Code 配置拓扑（实测）

- `/stocks/.claude` 是符号链接；Claude Code **能**经链接加载 `settings.json`（hooks）、`settings.local.json`（含 `autoMode`）与 skills
  （2026-09-06 探针验证）。`/auto-mode-setup` 向导**拒绝**写符号链接目录（"indirection gate"），改用 `claude/auto-mode/apply-auto-mode.sh` 应用。
- auto mode 规则分两层：用户级 `~/.claude/settings.json`（本机通用）+ 项目级 `claude/settings.local.json`（工作区事实与规则，gitignored）；
  生效配置 `claude auto-mode config`、内置默认 `claude auto-mode defaults`、AI 点评 `claude auto-mode critique`。
  分类器把 Agent 改写自己的 auto mode 规则视为 hard_deny（Auto-Mode Bypass）→ **由 Owner 跑脚本应用**，Agent 只准备 payload 并报告。
- `preflight.js` 的 D10 规则不豁免文件写入：Bash heredoc 正文里若同时出现 `ib:operator:cmd` 与 XADD / SET / DEL 等写动词会被拦
  （设计内的宁可误报）；写含该字面量的文档用 Edit / Write 工具，不改 guard。
- Claude Desktop 会话分组 `Trade. System` 与 `Ops - Plugin` 的 cwd 都是 `/stocks`：共享根 `CLAUDE.md`、hooks、auto mode 与
  记忆目录 `~/.claude/projects/-Users-vision-mac-trader-Desktop-stocks/memory/`；子 repo 的 `CLAUDE.md` 在触及该 repo 文件时自动加载。
- 治理缺口：子 repo 没有自己的 `.claude/settings.json`，会话若在子 repo 目录启动则**没有** preflight hook 与 auto mode 环境 → 会话一律在 `/stocks` 根启动。

---

## 9. 如何刷新本文件

本文件会随项目演进过期。刷新时：

1. 读 spine `bifrost-platform/config/ops-context.yaml` 的 `deployment` / `focus` / `milestones` / `decisions`
2. 读 `agentProtocolCatalog.ts` 的 `FORBIDDEN_ACTIONS` 与 `AGENT_MODES`
3. 磁盘扫描核对 repo 清单、端口、页面数
4. bump `parity-id`（`agent-facts-v<n+1>`）+ 更新 `generated:`
5. 跑 `bash scripts/check-agent-config-parity.sh`
