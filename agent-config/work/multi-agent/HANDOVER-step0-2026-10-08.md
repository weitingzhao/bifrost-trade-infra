# 交接简报：W-31 第 0 步执行线程

- **写给**：Owner 在「Ops Platform 瘦身」完成后新开的执行线程（建议标题：「W-31 第 0 步」）。
- **来自**：多 Agent 协作线程（2026-10-08，CLI 会话 f316b296）。这个线程继续负责讨论和决策；执行交给你。
- **你的角色**：第 0 步期间暂代「参谋长」：拆道、派给 Cursor、照报告验收、整理要 Owner 决定的事。运行时建好之前，这个角色由线程人工担任。

## 开工前先读（按顺序）

1. 工作区根的 `CLAUDE.md`、`AGENT_FACTS.md` §8c。
2. `agent-config/ADR-ops-architecture.md`：§1（Owner 只做三件事）、§5（规则集与发版策略）、§12（多 Agent 协作，整节）。
3. `agent-config/work/multi-agent/DESIGN-agent-runtime-2026-10-08.md`（v4），重点读第 10 节（第 0 步）。
4. `agent-config/work/multi-agent/STEP0-PLAN-2026-10-08.md`：本次要执行的计划（Owner 审过的版本以 git 为准）。
5. `agent-config/work/ops-arch/STATUS-*.md`：瘦身线程最后一版的状态，是第 1 天差异盘点的基线。
6. 记忆 `multi_agent_coordination_2026_10_08.md`：每个决定背后的来龙去脉。

## Owner 的工作方式（必须遵守）

- 一律用中文回复；UI 字符串和代码标识符用英文。
- **先讨论透，再落地**：方案选项里的「推荐」不等于落地许可；Owner 明说确认之后，才写任务、合分支、改配置（记忆 `feedback_discuss_before_landing`）。
- **Owner 只做三件事**：定目标、定规则、处理不可逆的事。送到他面前的每件事都要标明属于哪一件，并附上选项、推荐、以及不回复时会怎样。不要拿可以自动化的事去打扰他。
- **可见性**：要 Owner 知道的事，最终都要出现在 Console 上。在 D1 过渡层上线之前，先写进 WORK.md。
- 实现交给 Cursor（每条道一个会话，只推分支，写报告）；你照报告重跑验收，再合并（记忆 `feedback_cursor_implements_claude_verifies`）。

## 推送纪律（10-08 吃过亏）

- infra 的纯文档改动：在临时 worktree 里提交，用 `release.sh window && git push origin <sha>:refs/heads/main` 推送，推完把共享 checkout 用 `git merge --ff-only` 快进。**不要**先提交到共享 checkout 再推：一旦和远端分叉，`reset --keep` 会被 auto mode 拦下，只能让 Owner 手动对齐。
- 提交时只列自己改过的文件；新的 W-n 编号先在 WORK.md 登记，再派活。

## 第 1 天要做的

1. 按 `STEP0-PLAN` 第 1 节做差异盘点：只读，结果写回计划，标明哪些和 10-08 的数字不一样。
2. 按盘点结果修订计划，把修订点交给 Owner 确认。
3. Owner 确认后，在 WORK.md 里给 S0-1 … S0-9 分配 W-n 编号，写第 1 波的 Cursor 道：S0-1、S0-2、S0-8 的代码 rebase、S0-7 的代码 rebase、S0-4a。

## 不要碰的

- ops-arch 的范围：Console 的删减、W-32、W-33。
- Grok 留下的 LANE-N、LANE-M2，以及还债台账里观察中的项：这些归「还债试点」的第一个 mission，在运行时第 2 阶段处理，第 0 步不处理。
- D10，以及任何实盘交易相关的路径。
- 不在工作区根目录新建任何东西（S0-6 的守卫上线之前，靠自觉遵守）。

## 第 0 步做完之后

按 v4 第 12 节进入运行时第 0 阶段（单 Agent 基线）。开工前先和 Owner 确认，因为那时要建 `agentrt` 的表（属于架构级改动，要按 database-design 规范来）。

## 瘦身线程 10-10 移交

瘦身线程（CLI 会话 230292da）10-10 收口时补的。只列 10-08 之后新出现、归第 0 步的事；瘦身自己的状态看 `work/ops-arch/STATUS-2026-10-08.md`「10-10 周六」。

### 瘦身停在哪里

- W-32、W-33 两波都已上 PROD；第 5 阶段退出条件 10-09 满足：Agent 侧没有集群管理员、节点 root、子系统管理员凭证。
- 滚动重启 10-10 已做完（5 台内核 6.8.0-146；主库在 02）。瘦身计划结束，没有遗留给 Owner 的动作（Time Machine 10-10 已确认当天有备份）。

### 第 1 天盘点会看到的变化（和 10-08 的数字不一样的地方）

- `~/.kube/bifrost-k3s.yaml` 现在是只读身份 `bifrost-agent`；写集群走平台动作（根 `CLAUDE.md` §3 对照表）。管理员 kubeconfig、节点密钥（带口令）、子系统管理员密码都在 Owner 目录，preflight 拦引用。
- C / D 级动作：建单 → 给 Owner 链接 → `wait_for_request`。不默认调 `approve_request`（记忆 `feedback_approvals_wait_dont_popup`）。
- 集群内 registry 已有持久卷（`cicd/registry-data`，nfs-cold 200Gi）；`check_registry_images.py --live` 是验收。
- apply 流水线的 plan 用 `--field-manager=bifrost-applier`，diff 出错会打印并失败。
- 直接调用的 B 级 workactions 现在写审计（platform `efeaf69`）。

### 归第 0 步的新事项

1. **「批准后由系统执行」**（Owner 10-10 同意写方案，和 TD-286 同一份）。10-09 到 10-10 的实际情况：凡是要管理员 kubeconfig 或节点密钥的步骤，都是 Claude 给命令、Owner 手工执行、Claude 再核对，只因为执行者不存在。要点：
   - `owner_run_command` 需要一个执行者，放在带外操作面（.50），凭证只在那里；
   - 任何一处批准（Console、手机、会话）效果相同，等待中的会话自动继续（`wait_for_request` 已做到）；
   - 审批单要有短数字编号；通知里写清动作、环境、关键参数、发起线程、过期时间，并记录投递结果；
   - Console 审批页按状态分组，参数和 plan 输出要可读；
   - 会话里回「批 #n」可以批。
2. **TD-287**：gpu-server 的唤醒与关机归同一个执行者（WOL 不需要凭证；关机用一把只能执行 poweroff 的专用钥匙）。01 上那个服务现在每次关机都失败，还打印成功。
3. **TD-283、TD-284**：`release.sh dev` 的重启、插件与 pine 构建，都还绕不过 kubectl，要接到平台动作上。
4. **TD-285**（要 Owner 定）：applier 接管不了 `kubectl-client-side-apply` 拥有的字段。选 `--force-conflicts`，还是由 Owner 逐个迁移字段归属。
5. **TD-288**：01（唯一控制面）10-10 无关机过程地断掉又起来，原因未知。Owner 10-10 查了 UPS，正常，不再追硬件；台账里观察到 11-09。第 0 步里做告警那一半（节点非计划重启）。
6. **TD-289**（10-10 已上线，观察到 10-11 06:05Z）：Prometheus、Alertmanager 的数据原来在 emptyDir，10-10 滚动重启驱逐 01 时丢了 10 天的指标历史；Owner 定放 NAS，已改到 `nfs-hot` 的卷上并做过删 Pod 验证。盘点里凡是「读 Prometheus 历史」的数字，10-10 06:04Z 之前的都没有了。

### 这一轮学到的（细节在记忆里）

- 静态检查全绿不算数：apply 流水线有 4 个只有真跑才暴露的问题（`cluster_policy_changes_need_server_dry_run`）。
- 扫描要放阳性对照：本机没有 `timeout`，命令不存在时输出为空，看起来像「干净」（`empty_scan_needs_a_positive_control`）。
- 给 Owner 的命令放在一轮的最后一条消息里，Owner 用会话里的 bash 输入执行，输出直接可见。
- 「谁重启了它」先读开机时间和上一次开机的日志结尾，不要从下游症状倒推（TD-282 最初被写成 containerd 重启，实际是整机断电式重启）。
- 滚动重启第一次真跑（10-10）：drain 之前要查两样，零预算的 PDB 和放在 emptyDir 里的状态；同一条 Owner 命令被提交两次就会起两个脚本，执行类脚本要自己加锁；带口令的 ssh 提示有大约 2 分钟的时限。脚本现在有锁、重问口令和 `--done` 续跑。
