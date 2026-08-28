<!--
parity-ids: workspace-v4, language-v1, agent-modes-v2, trade-execution-freeze-v2, dev-services-v2, phase-execution-v2
对等文件: .cursor/rules/{workspace,language,bifrost-agent-modes,trade-execution-freeze,dev-services,phase-execution}.mdc
改任一侧必须同步另一侧并 bump 两侧版本号；校验: bash scripts/check-agent-config-parity.sh（= make check-agent-parity in bifrost-trade-infra）
-->

# CLAUDE.md — Bifrost 工作区

与本项目用户对话**一律使用中文回复**（无论用户用何种语言提问）。
UI 字符串与代码标识符使用 **English**；代码注释中英不限；文档中英不限。

> **事实基线：[`AGENT_FACTS.md`](AGENT_FACTS.md)** — repo 清单、端口表、已退役实体、运行环境、权威源链。
> 本文件只讲**规则**，不重复事实。两者冲突时以 `AGENT_FACTS.md` 为准，并修正本文件。

---

## 1. 三域架构（最高层结构）

Bifrost = 三个域，边界不可跨越（spine **D13**）：

| 域 | Repos | 数据库 |
|----|-------|--------|
| **Trade (OLTP)** | `bifrost-trade-{core,socket,worker,api,frontend,infra}` | `bifrost_{dev,stg,prod}` |
| **Research (OLAP)** | `bifrost-research` | `bifrost_golden_source` |
| **Ops (控制面)** | `bifrost-platform` + `bifrost-platform-plugin{,-market-data,-flex-query}` | 控制面状态 |

共享：`bifrost-ui`（`@bifrost/ui` 组件库）。详见 `AGENT_FACTS.md` §1–§2。

### 双飞轮 — 平台/业务解耦（最关键设计决策）

- **Flywheel A（Trade）** = 业务数据面 · **Flywheel B（`bifrost-platform`）** = 控制面
- `bifrost-platform` **永远不了解**：Greeks、IB 协议、SEPA、straddles、daemon 策略
- **验证测试**：把 `bifrost-platform` clone 到新集群、指向别的应用，Dev/Ops Agent 应开箱即用
- Trade repos **不得**修改 platform-api 路由或 Ops Console 架构页

任何涉及 `bifrost-platform` 的改动，先问：**这是平台通用能力还是 Trade 专属逻辑？**
是 Trade 专属，它就不应该进 `bifrost-platform`。

---

## 2. Agent 模式（开工前先确定）

做非平凡工作前，推断或询问当前属于哪个模式：

| 模式 | 何时 | 主要 repo | 禁止 |
|------|------|----------|------|
| **Product** | UI 页面、Dense UI、FE hooks | `bifrost-trade-frontend` | 不改 compose prod |
| **Ops** | Matrix、spine、K3s、release gate | `bifrost-platform`、`bifrost-trade-infra` | 不改 Trade 监控页（除非明确交叉） |
| **Promote** | 发布 / prod cutover / 环境提升 | Ops Console Promote + spine | 提议 cutover 前必须尊重 spine 的 `BLOCKED_ON` 与 Owner 决策 |
| **Research** | dbt / OLAP engines / Golden Source | `bifrost-research` | 只写 `dw_stock.*` / `features.*`；**不得**写 Trade DB 或 `raw_market.*` ingest |

**权威源**：`bifrost-platform/console/src/lib/architecture/agentProtocolCatalog.ts`（`AGENT_MODES` + `FORBIDDEN_ACTIONS`）
**治理优先级**：代码 → Console Governance catalogs → spine

**所有模式**：实盘交易 BLOCKED，见 §3。

---

## 3. ⚠️ D10 — 交易执行冻结（硬边界）

**状态：BLOCKED**（spine `decisions[id=D10]`，signed 2026-07-04）。

实盘交易（自动下单、daemon FSM `place_order`、实盘对冲、真实 IB 发单）是**最后才启用的能力**。
Ops Platform（火箭）与 Trade（载荷）必须先稳定；研究与分析尚不足以支撑交易。

**解锁需要两个条件同时满足**：Owner 明文书面指令（如「解禁交易执行」）**且** spine D10 → `UNLOCKED`。

### 禁止（所有模式）

- 为实盘自动交易扩容 `daemon` Deployment（STG 必须保持 `replicas: 0`）
- 移除或绕过 `k8s/overlays/{stg/daemon-scale-zero,prod/daemon-observe-safe}.patch.yaml`
- 在没有新的 Owner 批准 program 的情况下，把 S08 daemon execution / 实盘 `place_order` 接到 Gateway RPC
- 用 Monitor `POST /control/*` 武装实盘交易
- 写 `ib:operator:cmd`（唯一合法写入方是 Daemon 本身）
- 推进任何**主要目的是启用实盘发单**的变更

### 允许

部署 W1–W3 只读/观测面（monitor、ops、frontend、read-only API 域）；
改进 observe UI、health、quotes SSE、research 数据路径。

### 机械强制

`scripts/agent-guard/preflight.js` 在 `PreToolUse` 拦截上述动作。
该脚本**运行时读 spine 的 D10 状态**——闸门与 spine 同源，解锁只有一个开关。
被拦截时不要绕过、不要"修复" guard 文件，直接向 Owner 报告。

---

## 4. Dev 服务管理（bdev + tmux）

本地开发服务运行在 tmux session `bifrost` 中，由 `bdev` CLI 管理，声明在 `~/.bifrost-dev/sessions.yaml`。

| 服务 | 端口 |
|------|------|
| `platform-api` | 8780 |
| `platform-console` | 5180 |
| `trade-ui` | 5173 |
| `git-bridge` | 8785 |
| `probe-bridge` | 8786 |
| `prometheus-pf` | 9090（需 `KUBECONFIG`） |

**禁止**（`preflight.js` 拦截）：
- 在终端里长期直接跑整包 `run_platform.py` / `start.sh` / `run-local-ui.sh`
- 与 bdev 拆分 session 同时再跑整包 `run_platform.py`（双开抢端口、留 T 状态孤儿）
- 直接 `kill` 这些服务的进程 —— 用 `bdev restart <name>`
- 残留手动 `kubectl port-forward …9090`（造成假健康）

**优先用 MCP 工具而非 shell**：`list_dev_sessions` / `restart_dev_session` / `get_dev_session_logs`。
`bdev` 命令作为 fallback。读日志：`~/.bifrost-dev/logs/<name>.log` 或 `bdev logs <name> -n 200`。

---

## 5. 执行纪律

多步骤工程任务（Phase / Wave）遵循 **`.claude/skills/phase-execution/`**。要点：

- 开工前读 spine + 对应 SKILL.md；Owner 已定的方案不重新提议
- 每个逻辑单元完成后立即自检：Python `make lint && make test` · TS `npm run lint && npm run build` · Go `go build ./... && go test ./...`；失败自行修复
- **架构级决策不擅自做**（新 RPC / 新外部依赖 / 改公开接口 / 新增表或列）→ 列 2–3 个选项 + 推荐，等 Owner 确认
- 最小化变更范围；不引入 TODO / FIXME
- 完成后输出结构化 Phase 报告；**不自动开始下一个 Phase**（除非 Owner 已确认「批量执行」→ `.claude/skills/batch-execution/`）

数据库设计标准见 **`.claude/skills/database-design/`**（新增/修改 PostgreSQL 表时触发）。

---

## 6. Repo 级规范

各 repo 有自己的 `CLAUDE.md`，进入该 repo 的文件时自动加载。特别注意：

| Repo | 额外规范 |
|------|---------|
| `bifrost-trade-frontend` | `AGENTS.md` · Dense UI 系统（`.claude/skills/dense-ui/`）· 大改版用 `.claude/skills/frontend-design/` · DEV Inner Loop（D-IL1：验收在本机 Vite `:5173`，不是 Prod） |
| `bifrost-trade-core` | 版本管理：改公开接口必须同 PR bump `pyproject.toml`，破坏性变更需列出受影响下游并同步 `BIFROST_CORE_REF` |
| `bifrost-research` | D13 边界：只读 `raw_market.*`；写 `dw_stock.*` / `features.*`；不触交易执行 |
| `bifrost-analytics` | **已归档**，勿再改（已并入 `bifrost-research/src/bifrost_research/dbt/`） |

---

## 7. 双轨维护（Cursor ↔ Claude）

本项目同时被 Cursor Agent 与 Claude Code 使用，两侧各维护一套完整规则：

| Claude 侧 | Cursor 侧 |
|-----------|----------|
| `CLAUDE.md`（本文件） | `.cursor/rules/workspace.mdc` |
| `.claude/skills/` | `.cursor/skills/` |
| `.claude/commands/` | `.cursor/commands/` |
| `.claude/settings.json` hooks | `.cursor/hooks.json` |
| — 共用 —— | `AGENT_FACTS.md` · `scripts/agent-guard/preflight.js` |

**改动任一侧的规则，必须同步另一侧并 bump 两侧的 `parity-id`。**
提交前跑 `bash scripts/check-agent-config-parity.sh` 校验。

事实与硬边界**只有一份实现**（`AGENT_FACTS.md` + `preflight.js`），不复制到两侧。

### 存放位置

治理层实体在 **`bifrost-trade-infra/agent-config/`**（纳入 infra 版本控制与 CI），
工作区根的 `CLAUDE.md` / `AGENT_FACTS.md` / `.mcp.json` / `.claude` / `.cursor` / `scripts` 均为符号链接。
布局、链接重建命令与路径约定见 `bifrost-trade-infra/agent-config/README.md`。

