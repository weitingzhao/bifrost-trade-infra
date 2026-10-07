# Ops 架构落地（ops-arch）— 计划与 Cursor 规则

依据：`agent-config/ADR-ops-architecture.md`（Owner 2026-10-07 采纳）。本目录是它的落地计划与任务。
**分工**：Cursor 每个会话做一条道（`LANE-*.md`），只推分支、写报告；Claude Code 照报告验收、合并、按 Owner 审批发布、管台账。

## 阶段

| 阶段 | 目标 | 道 | 退出条件 |
|---|---|---|---|
| **1 地基与止血** | 告警送对地方；集群状态有第二份；维护者有清单；计划文件进版本控制；停掉 .50 夜间 LLM；第一次时间点恢复演练；查清节点补丁 | A1–A7（本目录） | 各道验收 PASS，Owner 批准的 apply 已执行 |
| 2 PROD 成为唯一控制面 | 申请单 + 审批（聊天 / 手机 / Console）；动作目录；MCP 改连 PROD（先读后写）；PROD RBAC 补齐；UniFi 凭证进 PROD | 第 1 阶段验收后再写 | 当天的发布与同步全部出现在 PROD 审计里 |
| 3 Console 按 7 个问题重组 | 先出「每页去向表」给 Owner 过目，再实现；退场 Agent 派发、Vision / Tier-B、发布驾驶舱、Guides | 同上 | Owner 过目通过 |
| 4 工作项与进度 | 工作项登记覆盖全部工作线；`Work:` 尾注 + 防线；进度视图（Console ⑦ + 导出页） | 同上 | 进度页能列出待签、在途、本周上线、卡住 |
| 5 维护者治理与凭证收口 | 平台后台循环导出上次成功时间；每晚集群内对账；滚动重启动作；Agent 交出管理员 kubeconfig | 同上 | 对账 0 漂移；Agent 侧无管理员凭证 |
| 6 Mac mini A 方案与网络分区 | 带外服务用独立账户；Agent 进虚拟机与 Agent 区；集群与存储区、运维区；UniFi VPN | 同上 | 分区规则在 git、经 Owner 审批生效 |
| 7 TWS 与交易区 | TWS 自动重启；交易区迁移（换 IP、IB Gateway 配置） | 最后单独谈 | — |

每个阶段的道在上一阶段验收后才写，细节会根据上一阶段的结果调整。

## 第 1 阶段：七条道，可以同时开

| 道 | 内容 | 仓库 · 分支 | 要 Owner 批的动作 |
|---|---|---|---|
| A1 | 告警改道：warning 送 PROD，STG 退出告警链路 | infra · `cursor/a1-infra` | helm upgrade |
| A2 | 集群状态第二份：etcd 快照 + Secret 加密件每天到 NAS | infra · `cursor/a2-infra` | kubectl apply |
| A3 | 维护者清单 v1 + 对账检查 | infra · `cursor/a3-infra` | 无 |
| A4 | 工作区根的计划 / 评审 / 任务文件进版本控制 | infra · main（纯文档） | **开工前 Owner 确认这些文件可以公开** |
| A5 | 停掉 .50 夜间 LLM；PROD 不再依赖笔记本 git-bridge | platform · `cursor/a5-platform`，infra · `cursor/a5-infra` | 在 .50 卸载两个 launchd 任务 |
| A6 | 第一次时间点恢复演练的清单、核对脚本与手册 | infra · `cursor/a6-infra` | 建临时恢复库、删除 |
| A7 | 节点补丁调查（只读）+ 滚动重启脚本（不执行） | infra · `cursor/a7-infra` | 周末滚动重启 |

跨道：A1 拥有 `scripts/k3s/values-kube-prometheus.yaml` 与 `scripts/check_alert_routing.py`；A2 的告警名用 `BifrostClusterStateBackup*`，由 A1 加进呼人的匹配规则。A2、A3、A6、A7 各自需要 Makefile 目标时，各加一行，合并冲突由 Claude Code 处理。

## Owner 自己做的（第 1 阶段）

1. **生成加密密钥给 A2**：Mac Pro 上 `brew install age && age-keygen -o ~/bifrost-cluster-state.agekey`；私钥另存一份到 NAS 与离线介质，**不要发给任何 Agent**；把输出里 `age1…` 开头的公钥贴给 Claude Code。
2. **Mac Pro 备份到 NAS**：系统设置 → 时间机器，目标选 NAS 的 SMB 共享（绿联 NAS 支持）。覆盖 Claude 记忆、`~/bifrost-backups`、本机 `.env` 等只在这台机器上的东西。
3. **A4 开工前**：确认工作区根的 `PLAN-* / REVIEW-* / REQUEST-* / LEDGER-*` 与 `cursor-tasks/` 放进**公开**仓库没问题（见 A4）。

## Cursor 共用规则

沿用 `/Users/vision-mac-trader/Desktop/stocks/cursor-tasks/README.md` 的全部硬规则（worktree、只列自己的文件提交、`lineage.sh` 补尾注、门禁、不发版、不写库、不改台账、D10），以及第 2 轮变更（代码一律只推分支）。本计划的差异：

- **读任务**：`git -C bifrost-trade-infra fetch -q origin && git -C bifrost-trade-infra show origin/main:agent-config/work/ops-arch/LANE-<道>.md`。ADR 同理：`…:agent-config/ADR-ops-architecture.md`。
- **报告**写到 `agent-config/work/ops-arch/reports/LANE-<道>.md`，从 origin/main 开一个独立 worktree 提交，推 main（纯文档）：
  `bifrost-trade-infra/scripts/release/release.sh window && git push origin <sha>:refs/heads/main`（同一条命令）。
- 报告格式：每一项一节——改动（仓库 · 分支 · 完整 SHA）、防线（文件 + 测试名）、门禁（命令 → 结果）、**验收（一条命令 + 预期）**、要 Owner 批（具体命令，原样可执行）、后续（新发现：`文件:行` + 一句话）。
- 访问 Mac mini（只读）：`ssh -o IdentitiesOnly=yes -i ~/.ssh/id_ed25519 vision@192.168.10.50`（.52 同）。访问 k3s 节点（只读）：`ssh -o IdentitiesOnly=yes -i ~/.ssh/bifrost_deploy vision@<ip>`。集群：`KUBECONFIG=~/.kube/bifrost-k3s.yaml`，**只读**命令。
