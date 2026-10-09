# Bifrost 工作项（登记）

> 进度是算出来的，不在这里改数字。这里只登记工作线：计划、Cursor 道，以及还没写进 `TECH_DEBT.md` 的事。债本身仍以 `TECH_DEBT.md` 为准，本文件不复制那些条目。
>
> **状态**沿用技术债的五种：`未开始` → `在做` → `观察中（到 MM-DD，看什么）` → `待你签收`；签收后技术债会删条目。阶段必须留在这份登记里，所以已经由 VERIFY 关闭的阶段写 `已验收`（不进待签、不进在途、不算卡住）。
>
> 字段：标题、类别（计划 / 道）、状态、现在、下一步、验收、关联。`匹配` 是提交编号（`LANE-…`），进度接口用它把提交接到这一条，不从正文里猜。
>
> 本批只整理仓库里已有的文件，没有改它们。有 `reports/` 且正文没有写「未执行」的 cursor 道，视为报告已交，不在这里重复。`VERIFY-phase1.md` / `VERIFY-phase2.md` 已 PASS 的 ops-arch 道同样不重复（返工后的 PASS 盖过原来的返工）。

## 条目

### W-1

**阶段 1 · 地基与止血**

- **类别**：计划
- **状态**：已验收
- **现在**：`VERIFY-phase1.md` 记 A1–A8 为 PASS，Owner 批准的 apply 已执行（2026-10-07）
- **下一步**：没有。后续观察写在各道报告里
- **验收**：`agent-config/work/ops-arch/VERIFY-phase1.md` 表内结论都是 PASS
- **验收结果**：PASS 2026-10-07
- **关联**：`agent-config/work/ops-arch/README.md`、`agent-config/work/ops-arch/VERIFY-phase1.md`

### W-2

**阶段 2 · PROD 成为唯一控制面**

- **类别**：计划
- **状态**：已验收
- **现在**：
  - B1–B4 和返工道在 `VERIFY-phase2.md` 都是 PASS；
  - 退出条件「当天的发布与同步全部出现在 PROD 审计里」，10-08 实测未满足：21 个发布和构建 run 里只有 5 个进了 PROD 审计，Trade `release.sh`、插件构建和手工建的 run 都绕过了；
  - **Owner 2026-10-08 把这条退出条件移交 W-31**：它就是 W-31 第 1 期「发布队列」的验收。本阶段在 ops-arch 内关闭。
- **下一步**：没有（归 W-31）
- **验收**：原退出条件已移交 W-31；本阶段只看 `VERIFY-phase2.md` 全部 PASS
- **验收结果**：PASS 2026-10-08（VERIFY-phase2 全部 PASS；退出条件移交 W-31，实测记录见 `STATUS-2026-10-08.md`「第 2 阶段退出条件核对」）
- **关联**：`agent-config/work/ops-arch/README.md`、`agent-config/work/ops-arch/VERIFY-phase2.md`

### W-3

**阶段 3 · Console 按 7 个问题重组**

- **类别**：计划
- **状态**：已验收
- **现在**：
  - 已上 PROD（platform `f9f696f`，10-08，`appr_35e3fb0d71cbdc3e`）；TD-208 已签收；
  - 删留复核 Owner 已定，清理道是 W-32（Cursor 在做）。
- **下一步**：W-32 验收 → STG → PROD（第一波）。去向表剩下的两行「部分」并进 W-33
- **验收**：README 退出条件：STG 上 Owner 过目通过后发 PROD（已满足）；W-32 上 PROD 后关闭
- **关联**：`agent-config/work/ops-arch/README.md`、`agent-config/work/ops-arch/PHASE3-pages.md`、`agent-config/work/ops-arch/PHASE3-review-2026-10-08.md`、`agent-config/work/ops-arch/LANE-W32.md`

### W-4

**阶段 4 · 工作项与进度**

- **类别**：计划
- **状态**：在做
- **现在**：infra 部分（本文件、`Work:` 尾注）已在 main。**2026-10-08 起剩余部分移交 W-31**（多 Agent 协作）：D1 的 platform 部分不合，⑦ 进度视图由运行时的任务数据给出（ADR §12 范围移交）
- **下一步**：由 W-31 决定 `cursor/d1-platform` 的去留，并在运行时设计里给出进度视图
- **验收**：进度页能列出待签、在途、本周上线、卡住（README 阶段表）
- **关联**：`agent-config/work/ops-arch/README.md`、`agent-config/ADR-ops-architecture.md`

### W-5

**阶段 5 · 维护者治理与凭证收口**

- **类别**：计划
- **状态**：在做
- **现在**：
  - LANE-E1 已在 PROD：PodMonitor、存活规则、每晚对账，10-08 手动对账 drift 0；
  - mini 的 operator-plane 有了 PROD viewer 令牌（platform `2052182`）；
  - 其余（凭证收口等）并入第二波 W-33。
- **下一步**：10-09 确认定时对账 0 漂移；W-33 讨论
- **验收**：对账 0 漂移；Agent 侧无管理员凭证（README 阶段表）
- **关联**：`agent-config/work/ops-arch/README.md`、W-33

### W-6

**阶段 6 · Mac mini A 方案与网络分区**

- **类别**：计划
- **状态**：未开始
- **现在**：README 写带外服务用独立账户、Agent 进虚拟机与 Agent 区、集群与存储区和运维区分开、UniFi VPN。道还没有写。**2026-10-08 移交 W-31**（多 Agent 协作）：它就是运行时 Agent 主机层（`agentd` 进 mini 虚拟机）的宿主（ADR §12 范围移交）
- **下一步**：由 W-31 在运行时第 2 阶段之前写道。**Owner 2026-10-08 晚：其中的网络分区（Server 区一分为四、UniFi 规则）暂缓，不在瘦身范围，时机成熟再单独立项**；带外独立账户与 Agent 虚拟机仍归 W-31
- **验收**：分区规则在 git、经 Owner 审批生效（README 阶段表；网络分区暂缓后由 W-31 重定）
- **关联**：`agent-config/work/ops-arch/README.md`、`agent-config/ADR-ops-architecture.md`

### W-7

**阶段 7 · TWS 与交易区（暂缓，不在瘦身范围）**

- **类别**：计划
- **状态**：未开始
- **现在**：Owner 2026-10-08 晚定为暂缓，不在 Ops Platform 瘦身范围：TWS 自动重启、交易区迁移（换 IP、IB Gateway 配置）都等时机成熟再单独立项
- **下一步**：没有；重新立项时另写计划
- **验收**：—（重新立项时再定）
- **关联**：`agent-config/work/ops-arch/README.md`「范围」

### W-8

**LANE-A6R · 恢复演练合成与核对脚本**

- **类别**：道
- **匹配**：LANE-A6R
- **状态**：已验收
- **现在**：
  - 代码 `42dba0d`（Cursor 的 `8d37a16` rebase 后）已合 main；
  - 验收时发现演练命名空间和只读 Secret 在 10-07 拆环境时已删，手册写错了，Claude 在 `f6b76f1` 改正并恢复了命名空间清单；
  - Owner 批准后已补记 10-07 的 PASS（ConfigMap `data/pg-recovery-drill-last-pass`），并 apply 了告警规则（10-08 22:11Z）；
  - TD-258 已进「待你签收」。
- **下一步**：没有。下一次演练是 2027 年 1 月第一个周一，演练前先按手册第 2 节重建只读 Secret
- **验收**：`agent-config/work/ops-arch/reports/LANE-A6R.md` 存在，且写明核对脚本自测通过
- **验收结果**：PASS 2026-10-08 `f6b76f1`（五个门禁在干净 worktree 复现 exit 0）
- **关联**：`agent-config/work/ops-arch/LANE-A6R.md`

### W-9

**LANE-C · Console 按 7 个问题重组**

- **类别**：道
- **匹配**：LANE-C
- **状态**：在做
- **现在**：任务在 `LANE-C.md`，去向表 `PHASE3-pages.md`。`reports/` 没有 `LANE-C.md`
- **下一步**：按去向表做完，报告写到 `reports/LANE-C.md`
- **验收**：`agent-config/work/ops-arch/reports/LANE-C.md` 存在，STG 上 Owner 过目通过
- **关联**：`agent-config/work/ops-arch/LANE-C.md`、`agent-config/work/ops-arch/PHASE3-pages.md`

### W-10

**LANE-D1 · 工作项登记与进度接口**

- **类别**：道
- **匹配**：LANE-D1
- **状态**：在做
- **现在**：infra 分支已合（登记、`Work:` 尾注）。platform 分支 `cursor/d1-platform` a7b8681（`GET /api/v1/progress`、MCP `get_progress`）**没合，2026-10-08 移交 W-31**，ops-arch 不再合它
- **下一步**：W-31 决定它是并进运行时，还是废弃
- **验收**：hook 测试、`check_work_trailers.py`、parity；platform `go test ./...` 与 `mcp/platform` 的 `tsc` 和 `npm test`
- **关联**：`agent-config/work/ops-arch/LANE-D1.md`

### W-11

**LANE-E1 · 维护者存活与每晚对账**

- **类别**：道
- **匹配**：LANE-E1
- **状态**：在做
- **现在**：任务在 `LANE-E1.md`。`reports/` 没有 `LANE-E1.md`
- **下一步**：做完写 `reports/LANE-E1.md`
- **验收**：`agent-config/work/ops-arch/reports/LANE-E1.md` 存在，且对账结果为 0 漂移
- **关联**：`agent-config/work/ops-arch/LANE-E1.md`

### W-12

**LANE-D · 文档事实更正的调查**

- **类别**：道
- **匹配**：LANE-D
- **状态**：已验收
- **现在**：`reports/LANE-D.md` 没有入库。TD-241 已在 `TECH_DEBT.md` 还债顺序第 11 波的「已还」里，纠正落地报告是 `cursor-tasks/reports/LANE-G.md`
- **下一步**：没有。不要为了补一份调查报告去改已经还清的债
- **验收**：`TECH_DEBT.md` 还债顺序里 TD-241 在「已还」，且 `cursor-tasks/reports/LANE-G.md` 在
- **验收结果**：PASS（TD-241 已还，报告在 LANE-G）
- **关联**：`agent-config/work/cursor-tasks/LANE-D-docs-inventory.md`、`agent-config/work/cursor-tasks/reports/LANE-G.md`、TD-241

### W-13

**LANE-E · 宏观日历补 2027 CPI 与非农**

- **类别**：道
- **匹配**：LANE-E
- **状态**：在做
- **现在**：任务在 `LANE-E-macro-calendar.md`（TD-180）。`reports/LANE-E.md` 没有。任务写明 2027 日程当时尚未发布
- **下一步**：BLS 发布 2027 日程后再补，或写报告说明仍未发布
- **验收**：`agent-config/work/cursor-tasks/reports/LANE-E.md` 存在
- **关联**：`agent-config/work/cursor-tasks/LANE-E-macro-calendar.md`、TD-180

### W-14

**LANE-E2 · 2026 非农写入宏观日历**

- **类别**：道
- **匹配**：LANE-E2
- **状态**：在做
- **现在**：任务在 `LANE-E2-macro-nfp-2026.md`（TD-180 的前半）。`reports/LANE-E2.md` 没有
- **下一步**：做完写报告
- **验收**：`agent-config/work/cursor-tasks/reports/LANE-E2.md` 存在
- **关联**：`agent-config/work/cursor-tasks/LANE-E2-macro-nfp-2026.md`、TD-180

### W-15

**LANE-M · 数据库角色矩阵防线**

- **类别**：道
- **匹配**：LANE-M
- **状态**：在做
- **现在**：任务在 `LANE-M-db-role-matrix.md`（TD-85 的防线）。`reports/LANE-M.md` 没有
- **下一步**：做完写报告，再由台账决定 TD-85 是否进待签
- **验收**：`agent-config/work/cursor-tasks/reports/LANE-M.md` 存在
- **关联**：`agent-config/work/cursor-tasks/LANE-M-db-role-matrix.md`、TD-85

### W-16

**LANE-P2 · 插件新鲜度改走 HTTP**

- **类别**：道
- **匹配**：LANE-P2
- **状态**：在做
- **现在**：任务在 `LANE-P2-plugin-freshness-http.md`（TD-256）。仓库里没有 `reports/LANE-P2.md`。`cursor-tasks/HANDOVER-2026-10-08.md` 写 STG 已在跑、PROD 待发
- **下一步**：报告入库；PROD 发版不在本道
- **验收**：`agent-config/work/cursor-tasks/reports/LANE-P2.md` 存在
- **关联**：`agent-config/work/cursor-tasks/LANE-P2-plugin-freshness-http.md`、`agent-config/work/cursor-tasks/HANDOVER-2026-10-08.md`、TD-256

### W-17

**LANE-RP · 发版策略授权**

- **类别**：道
- **匹配**：LANE-RP
- **状态**：在做
- **现在**：任务在 `LANE-RP-release-policy.md`。`reports/LANE-RP.md` 没有。提案在 `work/release-approval/`，ADR §5 记 Owner 已选策略，实现由本道做
- **下一步**：做完写报告。本道不批准、不发起发布
- **验收**：`agent-config/work/cursor-tasks/reports/LANE-RP.md` 存在
- **关联**：`agent-config/work/cursor-tasks/LANE-RP-release-policy.md`、`agent-config/work/release-approval/PROPOSAL-2026-10-08.md`

### W-18

**LANE-T2 · IB Gateway 状态与报价镜像开关**

- **类别**：道
- **匹配**：LANE-T2
- **状态**：在做
- **现在**：任务在 `LANE-T2-ib-status-and-quote-mirror.md`（TD-104 后续、TD-240 方案 A）。`reports/LANE-T2.md` 没有
- **下一步**：做完写报告
- **验收**：`agent-config/work/cursor-tasks/reports/LANE-T2.md` 存在
- **关联**：`agent-config/work/cursor-tasks/LANE-T2-ib-status-and-quote-mirror.md`、TD-104、TD-240

### W-19

**LANE-T3 · 删掉没人读的报价镜像**

- **类别**：道
- **匹配**：LANE-T3
- **状态**：在做
- **现在**：任务在 `LANE-T3-drop-quote-mirror.md`（TD-240，表先不删）。`reports/LANE-T3.md` 没有
- **下一步**：做完写报告
- **验收**：`agent-config/work/cursor-tasks/reports/LANE-T3.md` 存在
- **关联**：`agent-config/work/cursor-tasks/LANE-T3-drop-quote-mirror.md`、TD-240

### W-20

**LANE-V · 前端 regime 列与数据缺口措辞**

- **类别**：道
- **匹配**：LANE-V
- **状态**：在做
- **现在**：任务在 `LANE-V-frontend-regime-and-wording.md`（TD-145、TD-150）。`reports/LANE-V.md` 没有
- **下一步**：做完写报告
- **验收**：`agent-config/work/cursor-tasks/reports/LANE-V.md` 存在
- **关联**：`agent-config/work/cursor-tasks/LANE-V-frontend-regime-and-wording.md`、TD-145、TD-150

### W-21

**LANE-W · 只返回新鲜度的端点**

- **类别**：道
- **匹配**：LANE-W
- **状态**：在做
- **现在**：任务在 `LANE-W-freshness-only-endpoint.md`（TD-259）。`reports/LANE-W.md` 没有
- **下一步**：做完写报告
- **验收**：`agent-config/work/cursor-tasks/reports/LANE-W.md` 存在
- **关联**：`agent-config/work/cursor-tasks/LANE-W-freshness-only-endpoint.md`、TD-259

### W-22

**LANE-X · 四处永远取不到数的报价 JOIN**

- **类别**：道
- **匹配**：LANE-X
- **状态**：在做
- **现在**：任务在 `LANE-X-dead-quote-joins.md`（TD-260）。`reports/LANE-X.md` 没有。任务要求先量再决定
- **下一步**：做完写报告
- **验收**：`agent-config/work/cursor-tasks/reports/LANE-X.md` 存在
- **关联**：`agent-config/work/cursor-tasks/LANE-X-dead-quote-joins.md`、TD-260

### W-23

**LANE-D2 · 数据库准备（未执行）**

- **类别**：道
- **匹配**：LANE-D2
- **状态**：未开始
- **现在**：`reports/LANE-D2.md` 标题写「准备，未执行」。SQL / 清单在分支上，没有 apply、没有写库
- **下一步**：等 Owner 批之后才执行；执行不在本登记里自动发生
- **验收**：报告里的 Owner 执行步骤跑完，并在该报告写明结果
- **关联**：`agent-config/work/cursor-tasks/LANE-D2-db-prepare.md`、`agent-config/work/cursor-tasks/reports/LANE-D2.md`

### W-24

**阶段 0 · W1 回测 0.169/0.170 收尾上线**

- **类别**：计划
- **状态**：在做
- **现在**：`PLAN-phase0-foundation-2026-10-05.md` 写剩余工作：草稿 PR 转 ready、前端模拟器页签、发布 research、执行 ddl-apply、跑一次真实 run。计划文件没有写完成
- **下一步**：按计划的剩余工作收尾；发布和 ddl-apply 要 Owner 点头
- **验收**：用真实数据复跑计划里那组历史 run 的期权腿模板，前后差异要能用计划点名的项解释
- **关联**：`agent-config/work/PLAN-phase0-foundation-2026-10-05.md`

### W-25

**阶段 0 · W2 回测收敛**

- **类别**：计划
- **状态**：在做
- **现在**：计划写 B6 改真实发布日、B7 计入退市标的，收敛方案 Owner 已答复「先改名、改口径，不删表」。计划文件没有写完成
- **下一步**：按已定口径改名，不删表
- **验收**：事件回测、Canonical PnL、信号评估三类的口径与计划「收敛」一节一致，且没有删旧表
- **关联**：`agent-config/work/PLAN-phase0-foundation-2026-10-05.md`

### W-26

**阶段 0 · W4 每日持仓快照**

- **类别**：计划
- **状态**：在做
- **现在**：计划写快照表与账户级 NAV（Owner 已同意自加项）。计划文件没有写完成。PROD DDL 仍要先列清单再点头
- **下一步**：列出 PROD DDL 清单，等 Owner 确认后才执行
- **验收**：计划「W4」一节的主键和账户级 NAV 行在三套 Trade 库里存在，且写入作业有当天的行
- **关联**：`agent-config/work/PLAN-phase0-foundation-2026-10-05.md`

### W-27

**阶段 0 · W5 手工数据备份**

- **类别**：计划
- **状态**：在做
- **现在**：计划写每日逻辑 dump 到 NAS、每周冷副本、每月恢复演练。存储放置 Owner 已定（k3s-hot / k3s-cold）。异地副本计划写明不阻塞开工、仍未定
- **下一步**：按「存储放置」做热冷副本；异地副本另定
- **验收**：每日 dump CronJob 在跑，热副本保留份数与计划一致，且有一次恢复演练记录
- **关联**：`agent-config/work/PLAN-phase0-foundation-2026-10-05.md`

### W-28

**阶段 0 · W6 Pine 脚本 sidecar**

- **类别**：计划
- **状态**：在做
- **现在**：Owner 2026-10-05 定稿新增 W6。`LEDGER-pine-tradingview-gaps.md` 记录其后多批已经上线；计划文件本身没有把 W6 标完成。台账 §8 的重评还没到
- **下一步**：见 W-29。不要把台账里已上线的批次再做一遍
- **验收**：标准指标在 Research 里算；自有 Pine 脚本只经隔离 HTTP 服务跑，不进前端 bundle（计划 W6 定稿）
- **关联**：`agent-config/work/PLAN-phase0-foundation-2026-10-05.md`、`agent-config/work/LEDGER-pine-tradingview-gaps.md`

### W-29

**Pine 台账 · 下次重评**

- **类别**：计划
- **状态**：观察中（到 11-06，看机械来源前瞻样本与 Pine 重开条件）
- **现在**：`LEDGER-pine-tradingview-gaps.md` §8：约 2026-11-06 重评；重开条件提前出现就提前看
- **下一步**：到日期或重开条件出现时重评 §0，不在到期前改方向
- **验收**：重评写回该台账 §7 和 §0，并写明机械来源两段样本离门槛还差多少
- **关联**：`agent-config/work/LEDGER-pine-tradingview-gaps.md`

### W-30

**Pine 台账 · PROD 上存第一个用户脚本**

- **类别**：计划
- **状态**：在做
- **现在**：台账 §7 2026-10-07 行写 Trade 发布已含 Pine 前端，待 Owner 在 PROD 存第一个脚本（该表里的 W4，不是阶段 0 的持仓快照）
- **下一步**：Owner 在 PROD 存第一个脚本后，把结果写回台账 §7
- **验收**：PROD 上存在一个用户脚本，台账 §7 有对应的一行
- **关联**：`agent-config/work/LEDGER-pine-tradingview-gaps.md`

### W-31

**多 Agent 协作（ADR §12）**

- **类别**：计划
- **状态**：在做
- **现在**：
  - 设计 v4 已定稿：`work/multi-agent/DESIGN-agent-runtime-2026-10-08.md`。
  - ADR §1（Owner 的三件事）、§5（规则集）、§12（整节改写）已写入。
  - 2026-10-08 从 ops-arch 接手 W-4、W-6、W-10 的剩余部分。
  - Grok Bot 作为总调度的角色退场。
  - 「Code 代码 - 还债」已停，改作本架构的试点。
- **下一步**：等 ops-arch（瘦身）完成后，从第 0 步开始（设计第 10 节），先拆道，再按阶段推进。讨论阶段的待定项已经全部定完（最后一项：低频定时任务可以用订阅额度，界限写进规则集，Owner 2026-10-08 定）
- **验收**：
  - 第 0 步：新节点测试通过、Gitea 做主、根目录白名单的防线为 0。
  - 第 0 阶段：Gate A（T01、T02、T08、T10）通过，基准集出第一份报告。
  - 发布队列：当天所有发布与同步都出现在 PROD 审计里，包括 Trade 的 `release.sh`、插件构建和手工建的 run。这条是 ops-arch 第 2 阶段的退出条件，Owner 10-08 移交给本议题。10-08 实测的基线是 21 个 run 里只有 5 个进了审计。
- **关联**：`agent-config/ADR-ops-architecture.md` §1、§5、§12；`agent-config/work/multi-agent/`

### W-32

**ops-arch · 第 3 阶段之后的清理道（删留复核落地）**

- **类别**：道
- **状态**：已验收
- **匹配**：LANE-W32
- **现在**：
  - **已上 PROD**（10-09 00:47Z，`appr_ff50015c21c5d833`，run `bifrost-deliver-platform-prod-1791506638`，platform `3d3ea8a` / ui `9b635b2`）；STG 由 Owner 10-08 过目通过；
  - 发版前先把 `trust-overrides.yaml` 带进两个 overlay 的 ConfigMap（infra `ffcaeb2`、`6185067`）。STG 验收时发现文件没进 ConfigMap，L0 退成了 L1；已加防线 `check_trust_overrides`；
  - PROD 实测：退役路由 15 条 404、2 条 405，保留的 10 条 200；`research-loop-batch` = L0，来自文件；Console 7 页正常，前端包里没有 `remediation/start`；插件新鲜度正常；workers 重启后没有维护者误报；
  - 两台 mini 已用 `3d3ea8a` 重部署（`/agent/skills` 404，.50 告警中转正常）；手动对账 drift 0。
- **下一步**：没有。留到以后的清理项写在 `reports/LANE-W32.md`「Claude 验收与收尾」末尾；remediation 后端随 W-33 撤掉
- **验收**：`agent-config/work/ops-arch/reports/LANE-W32.md` 存在，四组门禁全过；STG 上本道删除的路由全部返回 404，`trust-matrix` 仍带 `research-loop-batch` 那条覆盖
- **验收结果**：PASS 2026-10-09（PROD `3d3ea8a`：退役路由 404 / 405、保留路由 200、`trust-matrix` 带 `research-loop-batch` L0 且来自文件；PROD 旧 ConfigMap `platform-trust-overrides` 经 Owner 批准已删，删后仍读到 L0）
- **关联**：`agent-config/work/ops-arch/LANE-W32.md`、`agent-config/work/ops-arch/PHASE3-review-2026-10-08.md`

### W-33

**ops-arch · 第 5 阶段收口（第二波）**

- **类别**：道
- **状态**：在做
- **匹配**：LANE-W33、LANE-W33R、LANE-W33B
- **现在**：Owner 10-08 定合并四件：① 凭证收口（mini 不再持有管理员 kubeconfig 与 admin 令牌、部署脚本不再同步、remediation runner 与 .52 hermes-gateway 定去留）；② PROD 经代理转到 mini 的 operator 级路由认 PROD 令牌；③ Console 显示待重启节点、滚动重启做成审批动作；④ ⑤ 页给 Research 与插件显示 STG / PROD 两列版本。先讨论分步，任务文件还没写
- **下一步**（第一批上线进度，10-09 03:3xZ）：
  - **已完成**：
    - LANE-W33R 返工验收通过（platform `0bf5285`），STG 由 Owner 过目通过；
    - PROD overlay 已合（infra `1a41be4`）；
    - PROD 已发：`appr_7971f07136244bec`，`0bf5285`。PROD api 读到 workers 写的 patrol 记录（200 条，最新 03:15Z）；
    - 两台 mini 已重部署：**mini 上没有管理员 kubeconfig 了**，`.env` 只剩 4 个键，runner、hermes-gateway、Nous Hermes 都已撤，`~/.hermes` 保留；
    - 待重启信号已 apply（5 台 k3s 节点 = 1）；
    - 集群内对账 drift 0；
  - **第一批全部上线（10-09 03:3xZ）**：Grafana helm upgrade（revision 16，只多了子路径两行），`https://ops.bifrost.lan/grafana/` 返回 200，Console 内嵌面板同源、不再被拦；两个环境 role-tokens Secret 只删了 `REMEDIATION_RUNNER_TOKEN` 一个键（Owner 批；没有重跑整份令牌脚本，避免顺手轮换其他令牌和读 admin 令牌）；
  - **第 2 步**：`LANE-W33B.md`，Owner 10-09 定「〇」节五件全部按推荐，交 Cursor：
    - `owner_run_command` 只记录审批、由 Owner 执行（原决定「平台用管理员身份执行」与 TD-204 冲突，作废）；
    - `apply_manifest` 走固定 Tekton 流水线加专用身份；
    - 第 3 步只读角色只在 research 和两个插件命名空间保留 exec；
    - 发版链另开 LANE-W33C，本道验收后写；
    - TD-271 并入；旧文字和 TD-270 也在这一道；
  - 写道时实测发现 TD-271：PROD 平台身份经 cicd 的 PipelineRun 和 Argo Application 仍能间接拿到集群管理员，已登记，并写进 TD-204 待签收行的「后续」；
  - 第 3 步在第 2 步验收后另派
- **验收**：第 5 阶段退出条件——对账 0 漂移；Agent 侧没有管理员凭证
- **关联**：`agent-config/work/ops-arch/LANE-W33.md`、`agent-config/work/ops-arch/LANE-W33B.md`、TD-271、`agent-config/work/ops-arch/README.md`「剩下的两波」、`agent-config/work/ops-arch/W33-credentials-2026-10-08.md`、W-5

## 本批没有登记的

- 阶段 0 的 W3：`REQUEST-w3-archive-before-delete-2026-10-05.md` 状态节写 A、B、C 全部完成。
- `REQUEST-symbol-paired-ddl-2026-10-06.md`：台账 §7 写 PROD CHECK 已放宽。
- 三份 REVIEW：开放动作已经收进阶段 0 计划，不另开条目。
- ops-arch 里 VERIFY 已 PASS 的道，以及 cursor-tasks 里报告已交且没有写「未执行」的道。
