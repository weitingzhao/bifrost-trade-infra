# Ops 架构落地（ops-arch）— 计划与 Cursor 规则

依据：`agent-config/ADR-ops-architecture.md`（Owner 2026-10-07 采纳）。本目录是它的落地计划与任务。
**分工**：Cursor 每个会话做一条道（`LANE-*.md`），只推分支、写报告；Claude Code 照报告验收、合并、按 Owner 审批发布、管台账。

## 阶段

| 阶段 | 目标 | 道 | 退出条件 |
|---|---|---|---|
| 1 地基与止血（**已验收**，见 VERIFY-phase1.md） | 告警送对地方；集群状态有第二份；维护者有清单；计划文件进版本控制；停掉 .50 夜间 LLM；第一次时间点恢复演练；查清节点补丁 | A1–A7（本目录） | 各道验收 PASS，Owner 批准的 apply 已执行 |
| 2 PROD 成为唯一控制面（**已上线**；退出条件 10-08 实测未满足，**Owner 当天移交 W-31**，本阶段在 ops-arch 内关闭） | 申请单 + 审批（聊天 / 手机 / Console）；动作目录；MCP 改连 PROD（先读后写）；PROD RBAC 补齐；UniFi 凭证进 PROD | B1–B4（见下） | 当天的发布与同步全部出现在 PROD 审计里 |
| **3 Console 按 7 个问题重组**（**已完成**：10-08 上 PROD `f9f696f`，清理道 W-32 10-09 上 PROD `3d3ea8a`） | 去向表 `PHASE3-pages.md`（Owner 10-08 批准）；任务 `LANE-C.md`（一条集成分支 `cursor/phase3-platform`）；并入 TD-208 剩余一半 | LANE-C | STG 上 Owner 过目通过后发 PROD |
| 4 工作项与进度（infra 部分已合；**剩余部分 2026-10-08 移交多 Agent 线程 W-31**） | 工作项登记覆盖全部工作线；`Work:` 尾注 + 防线。进度视图不在本计划：D1 的 platform 部分（`cursor/d1-platform`）本线程不合，Console ⑦ 保持第 3 阶段之后的样子 | `LANE-D1` 的 infra 部分 | 移交 W-31 |
| **5 维护者治理与凭证收口**（E1 10-08 落地，对账 0 漂移；其余并入第二波 W-33） | 平台后台循环导出上次成功时间；每晚集群内对账；滚动重启动作；Agent 交出管理员 kubeconfig | `LANE-E1`（workers 进监控、存活指标、补告警、每晚对账）；凭证收口先与 Owner 讨论分步 | 对账 0 漂移；Agent 侧无管理员凭证 |
| 6 Mac mini A 方案与网络分区（**2026-10-08 移交多 Agent 线程 W-31**；其中**网络分区** Owner 10-08 晚定为暂缓，不在瘦身范围） | 带外服务用独立账户；Agent 进虚拟机与 Agent 区；集群与存储区、运维区；UniFi VPN | 由 W-31 写 | 移交 W-31 |
| 7 TWS 与交易区（**暂缓，不在瘦身范围**，Owner 10-08 晚） | TWS 自动重启；交易区迁移（换 IP、IB Gateway 配置） | 时机成熟再单独立项 | — |

### 剩下的两波（Owner 2026-10-08 晚定）

剩余工作合并成两波，做完即结束本计划。移交 W-31 的和暂缓的见上面「范围」。

| 波次 | 内容 | 时间 |
|---|---|---|
| **第一波：收尾上线** | W-32 验收 → STG（Owner 过目）→ PROD → 重部署两台 mini（operator-plane 删了路由）→ 删旧信任覆盖 ConfigMap，Grafana 修法 Owner 定；**10-11 周日滚动重启**，并入「5 台自动更新加 `-updates`」（周六先改配置、装上积压的包，Claude 先列清单给 Owner 批，周日一次重启带上新内核）；确认定时对账 0 漂移；Owner 本机看 Time Machine 最近一次成功 | 到 10-11 |
| **第二波：第 5 阶段收口（W-33）** | 先讨论一次，再派一条道，合并四件：① 凭证收口——mini 不再持有管理员 kubeconfig 与 admin 令牌，部署脚本不再同步它们，remediation runner 与 .52 hermes-gateway 定去留；② PROD 经代理转到 mini 的 operator 级路由认 PROD 令牌；③ Console 显示待重启节点，滚动重启做成审批动作；④ ⑤ 页给 Research 与插件显示 STG / PROD 两列版本（③④ 补上第 3 阶段去向表的两行「部分」） | W-32 上线后 |

**现状盘点**：`STATUS-2026-10-08.md`（计划 vs 实际落地、恢复后的顺序）。10-08 傍晚暂停过一次，Owner 当天把恢复条件改为「ADR §1 改写定稿」；§1 已定稿（infra `bf27c80`），本计划已恢复。

## 范围（Owner 2026-10-08）

本计划的线程叫「Ops Platform 瘦身」，只做瘦身。范围移交记在 ADR §12 顶部「范围移交」一段，WORK.md 的 W-4、W-6、W-10 同步改过。

- **删留判据**（ADR §1 末尾）：对 platform 的每项功能问三个问题——Agent 经 API / MCP 用它吗？Owner 用它来批、签、看吗？有维护循环依赖它吗？三个都答「否」就删，删之前请 Owner 过目。
- **移交多 Agent 线程（W-31）**：第 4 阶段剩下的部分（D1 的 platform 部分、⑦ 进度视图）；第 6 阶段里的带外独立账户与 Agent 虚拟机；第 2 阶段的退出条件（当天发布与同步全进 PROD 审计 = W-31 发布队列的验收，Owner 10-08）。
- **暂缓，不在瘦身范围**（Owner 2026-10-08 晚，时机成熟再单独立项）：TWS 自动重启、交易区迁移（换 IP、IB Gateway 配置）、网络分区（Server 区一分为四、UniFi 规则）。
- **明确不做**——不设计、不实现，也不预留接口或挂载点：
  - 多 Agent 运行时：任务与租约、Agent 主机守护进程、交互总线、推理网关、额度账本；
  - 发布队列；
  - RP 发版策略（`cursor/rp-*` 两条分支不合）；
  - 认领与待办箱；
  - 工作项编号规则；
  - Grok Bot 相关的任何事（它暂停中：不验收 LANE-N / LANE-M2，不收尾它的台账）。

  碰到和这些有关的问题，在 STATUS 里记一句「归多 Agent 线程（W-31）」，不展开。
- **platform 发版**：照现在的方式，Owner 在 PROD Console 的审批页直接批。D10 不变。

### 给 Cursor 派道（2026-10-08 起）

- 新道编号用 `W-n`，派活前先在 `agent-config/WORK.md` 登记（取当时的最大号加一），避免和别的线程撞名。
- 每条道文件的「不做」一节，原样抄上面「明确不做」的清单，再加一句：**不改 `api/internal/approvals/` 的审批语义**（删除已退场功能的调用方除外）。
- 其余照下面「Cursor 共用规则」：只推分支、写报告、不发版、不 apply。

每个阶段的道在上一阶段验收后才写，细节会根据上一阶段的结果调整。

## 第 1 阶段：七条道，可以同时开

| 道 | 内容 | 仓库 · 分支 | 要 Owner 批的动作 |
|---|---|---|---|
| A1 | 告警改道：warning 送 PROD，STG 退出告警链路 | infra · `cursor/a1-infra` | helm upgrade |
| A2 | 集群状态第二份：etcd 快照 + Secret 加密件每天到 NAS | infra · `cursor/a2-infra` | kubectl apply |
| A3 | 维护者清单 v1 + 对账检查 | infra · `cursor/a3-infra` | 无 |
| A4 | 工作区根的计划 / 评审 / 任务文件进版本控制 | infra · main（纯文档） | 无（Owner 10-07 已确认可公开） |
| A5 | 停掉 .50 夜间 LLM；PROD 不再依赖笔记本 git-bridge | platform · `cursor/a5-platform`，infra · `cursor/a5-infra` | 在 .50 卸载两个 launchd 任务 |
| A6 | 第一次时间点恢复演练的清单、核对脚本与手册 | infra · `cursor/a6-infra` | 建临时恢复库、删除 |
| A7 | 节点补丁调查（只读）+ 滚动重启脚本（不执行） | infra · `cursor/a7-infra` | 周末滚动重启 |

跨道：A1 拥有 `scripts/k3s/values-kube-prometheus.yaml` 与 `scripts/check_alert_routing.py`；A2 的告警名用 `BifrostClusterStateBackup*`，由 A1 加进呼人的匹配规则。A2、A3、A6、A7 各自需要 Makefile 目标时，各加一行，合并冲突由 Claude Code 处理。

## Owner 自己做的（第 1 阶段）

1. **生成加密密钥给 A2**：Mac Pro 上 `brew install age && age-keygen -o ~/bifrost-cluster-state.agekey`；私钥另存一份到 NAS 与离线介质，**不要发给任何 Agent**；把输出里 `age1…` 开头的公钥贴给 Claude Code。
2. **Mac Pro 备份到 NAS**：系统设置 → 时间机器，目标选 NAS 的 SMB 共享（绿联 NAS 支持）。覆盖 Claude 记忆、`~/bifrost-backups`、本机 `.env` 等只在这台机器上的东西。
3. ~~A4 开工前确认可公开~~：Owner 10-07 已确认。

## Cursor 共用规则

沿用 `/Users/vision-mac-trader/Desktop/stocks/cursor-tasks/README.md` 的全部硬规则（worktree、只列自己的文件提交、`lineage.sh` 补尾注、门禁、不发版、不写库、不改台账、D10），以及第 2 轮变更（代码一律只推分支）。本计划的差异：

- **读任务**：`git -C bifrost-trade-infra fetch -q origin && git -C bifrost-trade-infra show origin/main:agent-config/work/ops-arch/LANE-<道>.md`。ADR 同理：`…:agent-config/ADR-ops-architecture.md`。
- **报告**写到 `agent-config/work/ops-arch/reports/LANE-<道>.md`，从 origin/main 开一个独立 worktree 提交，推 main（纯文档）：
  `bifrost-trade-infra/scripts/release/release.sh window && git push origin <sha>:refs/heads/main`（同一条命令）。
- 报告格式：每一项一节——改动（仓库 · 分支 · 完整 SHA）、防线（文件 + 测试名）、门禁（命令 → 结果）、**验收（一条命令 + 预期）**、要 Owner 批（具体命令，原样可执行）、后续（新发现：`文件:行` + 一句话）。
- 访问 Mac mini（只读）：`ssh -o IdentitiesOnly=yes -i ~/.ssh/id_ed25519 vision@192.168.10.50`（.52 同）。访问 k3s 节点（只读）：`ssh -o IdentitiesOnly=yes -i ~/.ssh/bifrost_deploy vision@<ip>`。集群：`KUBECONFIG=~/.kube/bifrost-k3s.yaml`，**只读**命令。

## 第 2 阶段：四条道，可以同时开

| 道 | 内容 | 仓库 · 分支 | 要 Owner 批的动作 |
|---|---|---|---|
| B1 | 动作目录 + 申请单 / 审批 API（平台执行、审计） | platform · `cursor/b1-platform` | 发版（Claude Code 申请） |
| B2 | Console「待你批」页 + 手机推送（relay 加 notify） | platform · `cursor/b2-platform`；infra · `cursor/b2-infra` | 发版；在 .50 重新部署 operator-plane；建推送用 Secret |
| B3 | MCP 改连 PROD（先读后写）+ 聊天里批准的工具 | infra · `cursor/b3-infra`（agent-config）；platform · `cursor/b3-platform`（mcp/） | 应用 Claude 用户级权限（`apply-auto-mode.sh`）；切换写操作 |
| B4 | PROD 权限补齐、STG 关掉残留维护、UniFi 凭证进 PROD、告警 webhook 改用 reporter | infra · `cursor/b4-infra`；platform · `cursor/b4-platform` | 建 UniFi Secret；合并（Argo 会改集群） |

合并顺序：B1 先合，B2 / B3 在 B1 上 rebase 后合；B4 独立。三条道都按下面的接口约定写，不要等 B1 合并。

### 接口约定（B1 实现，B2 / B3 照此调用）

- `GET /api/v1/actions` → `[{id, tier, description, params}]`，`tier` ∈ `A|B|C|D|X`（ADR §5）。
- `POST /api/v1/approvals`（operator 及以上）`{action, params, reason, rollback}` → `201 {id, action, tier, params_hash, status:"pending", requester, expires_at}`。
  B 级动作返回 `400`（直接调用即可）；X 级返回 `403`。请求头 `X-Bifrost-Session` 记为 `requester`。
- `GET /api/v1/approvals?status=pending|all`、`GET /api/v1/approvals/{id}`（viewer 及以上）。
- `POST /api/v1/approvals/{id}/approve`（**admin**）`{channel: "chat"|"phone"|"console"}` → 平台**用批准时的参数**立即执行，返回 `{status:"executed"|"failed", result|error}`。
- `POST /api/v1/approvals/{id}/reject`（admin）`{reason}`。
- 状态：`pending → executed | failed`；`pending → rejected | expired`（24 小时）。一次批准只执行一次。
- C / D 级动作的原有直调端点：没有对应已执行的申请就返回 `403 {"error":"approval required","action":…}`。
- 申请单存平台状态（statefile，PROD 落 ConfigMap）；每次创建、批准、拒绝、执行都写审计。

### 第 2 阶段验收后（2026-10-07）

B2、B4 通过；B1、B3 要返工，Owner 选择聊天批准方案 B（见 ADR §5）。返工道：`LANE-B1R.md`（platform 集成分支 `cursor/phase2-platform`）、`LANE-B3R.md`（infra `cursor/b3-infra`）。上线顺序：B1R 发版到 PROD → 合 b2-infra、b4-infra → 建两个 Secret、apply RBAC、换 webhook 令牌、.50 重部署 operator-plane → 合 B3R 并让 Owner 应用权限与令牌文件。详见 `VERIFY-phase2.md`。
