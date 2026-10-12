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
- **方向（Owner 2026-10-12 12:30：「按这个分，后续步骤指做真实的工作」）**。起因：他问打地基的这些以后会不会都没用。统筹方的判断是分两类——**规则和护栏**（谁能对正式环境做什么、什么时候必须找他：审批、通知、发版策略、急停、CI 门禁、等待 / 停线 / 指派几条规矩）不管以后怎么协作都要有；**协作的机制**（调度脚本、心跳包装、看护、手工看板、主机守护进程、自建运行时）很可能被各家厂商的现成功能取代，这两天的问题是把机制当护栏来做。定下来的做法：护栏接着做、做实；机制各停在安全的位置并写明恢复条件（W-66、W-67、W-57、W-50、W-64、W-56 的全自动部分、W-62 的整页设计，以及后面几个阶段的运行时）；然后用现在这套协作去做真实的工作，回头按实际运作决定机制补哪一块。只有跨厂商（一家写、另一家审）是厂商不会替我们做的，机制里只保这一小块。下面「计划调整」第 1 条（搬到 mini 提前）被这条取代；第 2–5 条照旧。推翻：「方向撤回」。
- **Owner 2026-10-12 12:36：「接口同意，先把护栏做完再说」**。① 护栏第一项的第二半（TD-317）给心跳接口加一个可选字段，他同意了（按 CLAUDE.md §5，改公开接口要他点头）。② 真实工作先不点，护栏六项做完再说。
- **Owner 2026-10-12 12:39：总的次序**。原话：先把多 Agent 架构整体做好以后再来还技术债；那些技术债不是一天两天了，不差多等等。统筹方的理解（已向他复述，等他纠正）：次序是护栏六项 → 用这套协作做真实的工作并回头看机制 → 技术债；「整体做好」按当天定的分法算（护栏做实、机制回头再看），不是把搁置的机制重新捡起来。护栏里本来就含的几条债（TD-316、TD-317、TD-315、TD-295、TD-312、TD-309、TD-320）照做；其余技术债不由本条目主动安排。
- **方向补一处（Owner 2026-10-12 15:01：「先做派工流水线」）**。他的话：今天这些问题很大原因是协作进展由统筹方手工维护，多 Agent 协作不能靠手工维持，所以他想推进到让系统来做统筹方现在的工作。统筹方的记录：中午搁置的五条里，W-66 正是「让系统做手工的事」的那一条，当时归进机制一并停了，分得太粗。**只恢复 W-66，做薄**：先用起来、不追求可信；修掉真用时撞出来的缺口；统筹方派活和收结果改走一条命令、由它记事件，页面从事件生成；新旧并排，对不上的就是要修的；它永远不参与正式环境的决定。次序：护栏第 ① 项收完 → W-66 三片 → 护栏 ② 到 ⑥。别的机制（W-67、W-57、W-50、W-64、全自动发布、后面阶段的运行时）照旧搁置。推翻：「派工流水线放回去」。
- **计划按实际重排（Owner 2026-10-12 15:26 提出；下面是统筹方排的版本，他 15:29 回「好的，按这个排」）**。原来的划分是「第 0 步打地基 + 阶段 0 到 5」，第 0 步的六条完成标准里有两条属于当天搁置的东西（按规则自动放行的发布、运行时的数据库和队列），照它永远走不出第 0 步；阶段 0 到 5 写的是自建运行时，也已搁置。重排成按轮次：
  - **已经在用的**：审批和手机通知、编号和状态机、Needs you、发版策略（测试环境自动）、没有信任锚时拒绝冻结、CI 门禁、线程心跳、Console 清理等 15 条。
  - **第 1 轮（现在，约一周）**：护栏六项，加派工流水线三片。做完的标准：六项都上了正式环境；统筹方不再手改「在跑 / 做完」这类状态。
  - **第 2 轮**：用这套协作做 Owner 点的真实工作；同时记下哪些环节还靠手工、在哪里卡住，轮末回头看，决定机制补哪一块。
  - **第 3 轮（内容待定）**：按第 2 轮回头看的结论定。候选是现在搁置的几条：搬到 mini（虚拟机）、全自动发布、按额度分流、整页进展设计、自建运行时的任何一部分。不预设都要做。
  - **排在多 Agent 架构之后**：技术债（Owner 当天定）。**不在计划里**：后移的 7 条小项。
- **护栏的先后（统筹方 2026-10-12 12:30 排的，可以改）**：① Needs you 误报的平台一半、每条有动作（W-62；2 片，跟下一版 platform，Owner 批一张发布单）。② 流水线自查「CI 绿、STG 同一提交」（W-56；1 片，Owner 把流水线应用到集群一次，TD-309 那条命令一起）。③ CI 门禁「故意失败会被拦」的另一半（TD-315；1 片，同一版 platform）。④ Gitea 备份（W-41；1 片，Owner 2 次）。⑤ 按固定提交和镜像摘要部署（TD-295；2 片，难）。⑥ Console 只留一处登录（TD-312；按缩小后的目标重出设计 1 片、实现 2 片，难；Owner 批一张发布单）。合计约 10 片，其中难的 3–4 片，约一周，把握中。小的随手做：TD-320 的两处文档、TD-309。
- **计划调整（2026-10-12 10:25，统筹方按第 0 步头两天的教训定；Owner 当天说：第一次做、很多事始料不及，按经验和教训做实际调整）**。要推翻哪一条，说「调整第 N 条撤回」。
  1. （2026-10-12 12:30 被上面的「方向」取代：搬到 mini 搁置。）**搬到 mini 提前，不再排在调度脚本做完之后。** 两天里的停顿多数出在「跑在一台会睡的开发机上」：夜里没人掐表、看护随线程断、并行把机器压满、统筹方单点（教训 105、106，`RUNTIME-PLACEMENT` 第 10 节）。调度脚本并排跑的这一周（最早到 10-19）本来就是等的时间，用来做 W-67 的设计和一台 mini 的试点，W-57（主机心跳）和 A19（孤儿巡检）并进同一个「主机守护进程最小版」。要 Owner 的几样（每台登录各家命令行、`RUNTIME-PLACEMENT` 第 7 节的几项）等设计出来一次带给他。
  2. **难的线同一时间只开一条实现。** W-56（冻结协议）和 W-66（调度脚本）第一片各用了 5–6 轮，两条同时开时复核和验收排队、机器过载。难的线一条在实现，另一条只做设计或补测试；空出来的并行度给容易的条目（W-41、W-57、台账里的小修）。有了第二台主机再放宽。
  3. **难的线切得更小，三轮没过就改走「不可信地合进主线」。** 一片不超过约 8 条规则，每条带「只有它能拦住的用例」和一处种错（教训 102、103）。还没接线的地基代码三轮没过复核时，统筹方在停线时写下的建议就是：合进主线、标明不可信、列必须修的清单、并排跑——不再等到第 6 轮。停线和「不接线」照旧，走的是等待规矩第 4 类。
  4. **估算换单位。** 「片」按实测的轮数折成天：难的线一片约一天，容易的约两三个小时。第 0 步收窄之后还剩约 40 片，其中难的约 18 片；难的线串着做，所以第 0 步做完大约在 11 月初，把握低，每晚按当天实际重算。
  5. **后面的阶段到第 0 步出口再重排，现在不改。** 现在手工做的就是阶段 0 到 2 的人肉版；调度脚本、等待规矩、主机守护进程最小版做出来之后，那几个阶段的内容会变。教训已经逐条挂到设计上（`DESIGN-agent-runtime` 第 20 节、`OWNER-SURFACE` A14–A19、`RULE-waits`、`RUNTIME-PLACEMENT` 第 10 节），重排时以它们为输入。
- **下一步**：等 ops-arch（瘦身）完成后，从第 0 步开始（设计第 10 节），先拆道，再按阶段推进。讨论阶段的待定项已经全部定完（最后一项：低频定时任务可以用订阅额度，界限写进规则集，Owner 2026-10-08 定）
- **验收**：
  - 第 0 步：新节点测试通过、Gitea 做主、根目录白名单的防线为 0。
  - 第 0 阶段：Gate A（T01、T02、T08、T10）通过，基准集出第一份报告。
  - 发布队列：deliver、build、apply 三类 run，加上 Argo 同步（包括推 main 触发的自动同步），当天全部出现在 PROD 审计里，包括 Trade 的 `release.sh`、插件构建和手工建的 run（口径 Owner 2026-10-10 定，STEP0-PLAN 0.3 节卡 3）。这条是 ops-arch 第 2 阶段的退出条件，Owner 10-08 移交给本议题。基线：10-08 是 21 个 run 里只有 5 个进了审计；10-10 重测，deliver 和 build 10-09 是 15/15、10-10 到 06:30Z 是 12/15（缺 TD-284 的手工 run），apply 不记 run 名，Argo 自动同步基本没有记录。
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
- **状态**：观察中（到 10-11：周日滚动重启用新节点密钥跑通；退出条件 10-09 已实测满足）
- **匹配**：LANE-W33、LANE-W33R、LANE-W33B、LANE-W33BR、LANE-W33C、LANE-W33D
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
  - **LANE-W33B 验收未过（10-09）**：门禁全过，但审出能绕过审批的路，合并和 apply 前必须修，写成返工道 `LANE-W33BR.md`：
    - 流水线参数直接拼进 shell，B 级的「计划」就能以 applier 身份执行任意命令；
    - 策略检查用 awk 解析，flow 风格或 JSON 文档不检查却照样 apply，能藏 daemon（D10）；
    - 准入策略漏了 Tekton 远程解析器、secret 工作区和 hostPath、applier 写的 Pod 规格（hostPath 和能读全集群 Secret 的账号）、Argo 的 `spec.sources`；
    - 只读库账号停在两个整数计数列上，属误报；Owner 10-09 回「数据库照做」，并入 LANE-W33BR 第五节；
  - **LANE-W33BR 验收通过（10-09）**：platform `e2d5137`，infra `1a9b408`。Claude 补了一笔：4 条准入策略的 `matchNames` 字段非法，server 端 dry-run 会拒收，已改成 matchLabels，dry-run 96 个对象全部接受。上线按 `reports/LANE-W33BR.md`「Claude 验收」第 6 条拆分合并，每一步等 Owner 批；
  - **第一批上线（Owner 10-09 批 A–E）**：
    - A：platform main 快进到 `e2d5137`；infra 第 1 部分 `c26df43` 已合（去掉了 PROD overlay 和 AGENT_FACTS 那一行），STG 平台已同步、Healthy；
    - B：`k8s/platform-rbac` 已 apply，含 applier 身份、平台的 Job 权限、6 条准入策略和 AppProject `bifrost`；
    - D：两条 `--live` 检查都通过，拒绝原因逐条核对过，8 个反例都是被对应的策略拒绝；平台和 `tekton-deliver` 发起同步照常放行；
    - E：`k8s/cicd/tekton/apply-manifest` 已 apply；
    - C：auto mode 拦下后由 Owner 在终端执行，5 个 Application 已迁进 `bifrost`，`default` 已清空。之后 bifrost-research 的同步失败：它在 data 里有一个 NetworkPolicy，而项目目标漏了 data。补上 data（`96dc299`，Owner 执行）后，经平台 `gitops_sync_app` 同步到 `5029084`，Owner 批准，清单无变化，同步成功；
    - TD-271 转「待你签收」（`--live` 全过），tekton-trigger 的同类问题登记为 TD-272；
  - **STG / PROD 已发（10-09，Owner 批）**：
    - STG `bifrost-deliver-platform-1791557903`；
    - infra 第 2 部分 `1b11c5b`：PROD 的 ConfigMap 原地更新，没有触发滚动；
    - PROD `appr_dfb9a356c8ca7dce` → `bifrost-deliver-platform-prod-1791558391`，platform `e2d5137`，ui `9b635b2`；
    - PROD 动作目录 35 条（新增 6 个）；api 和 workers 没有报错；Console、Grafana 返回 200；remediation 和 hermes 的健康接口返回 404；
    - TD-270、TD-271 已签收；
  - **第 2 步完成（10-09，Owner 批冒烟和 DDL）**：
    - PROD 冒烟 6 个动作都实际跑通：
      - 计划与执行：bifrost-dev 的冒烟 ConfigMap，字段管理者是 `bifrost-applier`，之后已删除；
      - `create_job_from_cronjob`：maintainer-reconcile，drift 0；
      - curl 探针：带 wait-net 初始化容器，不挂账号令牌；
      - `delete_finished_jobs`；
      - `owner_run_command`：`appr_a0d489f1cdb4c2a7` 已驳回，平台没有执行；
    - 冒烟时修了流水线的 3 个问题，都是之前从没真跑过、只做了静态检查导致的，每个都加了静态防线：参数没传给任务（`c96ca82`）、网页归档地址不认凭证（`789c955`）、结果没有提升到 PipelineRun（`278f391`）；
    - Gitea 镜像要等同步才能用新提交，登记为 TD-273；
    - `agent_reader` 已在 PROD 建好：DDL 的 commit 和 verify 通过，role-matrix 0 差异，Owner 已设密码并写入 `~/.pgpass`；四个库都能读，CREATE 和 UPDATE 被权限拒绝；AGENT_FACTS 已写明用法；
  - **下一步**：
    - 发版链 `LANE-W33C.md`：Owner 10-09 定「〇」节四件，全部按推荐，交 Cursor。**10-09 验收通过**（Claude 补了两笔：调用方参数只能是 revision SHA，platform `00036f5`；release.sh 改读 PROD 令牌，infra `b33d735`），上线顺序见报告「Claude 验收」第 5 条，每一步等 Owner 批：
    - **LANE-W33C 已上线并真跑（10-09，Owner 批 A–F）**：
      - platform `00036f5` 已上 STG 和 PROD；infra 分两部分合（`f1fdcb6`、`e16c8aa`）；三份 Tekton 对象已 apply；
      - 真跑 STG Trade、PROD 钉死（Owner 在 Console 批）都通过；插件构建通过；
      - 新发现两件：窗口释放缺 RBAC，已修并 apply（`6d85724`）；插件 `k8s/base` 被拒（TD-275），后者挡着第 3 步的插件发版；
      - TD-273 转「待你签收」；

      - PROD pinned run 改成 Pipeline 加逐仓参数；
      - 发布窗口归平台；
      - Gitea 镜像同步交给平台（顺带修 TD-273）；
      - `start_pipeline_run` 带通用参数；
    - TD-275 已修并验收（10-09，Claude 直接修，Owner 批 apply 和 PROD api 重启）：market-data 插件「计划 → C 级 apply」全程走通，线上无改动；顺带修好了 C 级 apply 判断「在 main 上」的方式（Gitea 1.21 没有 compare 接口）；TD-273 已签收；新登记 TD-276；
    - **第 3 步**：讨论材料 `W33-step3-2026-10-09.md`，Owner 10-09 定「〇」节四件，全部按推荐，写成 `LANE-W33D.md` 交 Cursor：
      - 新发现：节点 root 实际靠 ssh-agent 里的 `id_rsa`（也是 GitHub 密钥），`bifrost_deploy` 没授权到任何节点；
      - 本机 `.env` 和 gitignore 的 Secret 文件里还有 Trade 管理员、UniFi、redis-ib、DB 属主轮换等管理员级凭证；
      - DB 日常密码归 TD-85；
    - **第 3 步完成（10-09，Owner 执行 1–6 步，Claude 逐步核对）**：
      - infra 第 1 份 `51e2240`、读权限补齐 `c635fbc`、文档第 2 份 `76cbf90`（AGENT_FACTS §8c、CLAUDE.md / workspace.mdc parity v18、ADR §5 三条接受风险）；
      - `~/.kube/bifrost-k3s.yaml` 是 `bifrost-agent`，管理员那份在 Owner 目录；本机 bdev platform-api 与 prometheus-pf 跟着只读；
      - 节点：新密钥带口令、不进 ssh-agent 也不进钥匙串；6 台的 `id_rsa` 那行已删，Agent 侧默认配置与 `id_rsa` / `id_ed25519` 都被拒；`bifrost_deploy` 已删；
      - `rolling-reboot.sh` 改为能问口令、不读 `~/.ssh/config`、`systemd-run` 排重启、`--execute` 用 Owner kubeconfig（`6932245`）；
      - `.env` 三份共 10 个键与 `k8s/base/secrets` 6 份已搬进 Owner 目录；本机 platform-api 重启后进程里没有 `UNIFI_*`；
      - preflight 补丁已应用（`8213875`，112 条通过），实测 5 条拦截生效；第 2 份补丁 `preflight-w33d-2.patch`（kubeconfig 值遇 `;` 误拦、冒号列表与别处同名副本漏拦）已应用（`adeabc0`，119 条通过，实测放行与拦截都对）；
      - 验收：`check_agent_access.py --live` ok；`release.sh window` 与 `stg --dry-run` exit 0；`check_maintainers --live` drift 0；本机没有其他可连 k3s 的 kubeconfig；B 级冒烟（Owner 允许后）`create_job_from_cronjob` 202、Job 输出 drift 0、`delete_finished_jobs` 200；
      - 新登记 TD-277（两个 `--live` 检查要模拟身份）、TD-278（插件 6 个 redis-ib 脚本读不到搬走的密码）、TD-279（直接调用的 B 级 workactions 不写 PROD 审计）；
  - 10-09 07:00Z 定时对账 drift 0；
  - 写道时实测发现 TD-271：PROD 平台身份经 cicd 的 PipelineRun 和 Argo Application 仍能间接拿到集群管理员，已登记，并写进 TD-204 待签收行的「后续」；
  - 第 3 步在第 2 步验收后另派
- **验收**：第 5 阶段退出条件——对账 0 漂移；Agent 侧没有管理员凭证
- **关联**：`agent-config/work/ops-arch/LANE-W33.md`、`agent-config/work/ops-arch/LANE-W33B.md`、TD-271、`agent-config/work/ops-arch/README.md`「剩下的两波」、`agent-config/work/ops-arch/W33-credentials-2026-10-08.md`、W-5

### W-34

**W-31 第 0 步 · S0-10 根目录 AGENTS.md**

- **类别**：道
- **状态**：已验收
- **现在**：已落地（Owner 10-10 定卡 1 = A）：`agent-config/AGENTS.md` 只放指针，根目录链接已建；README 重建命令加了一行；`CLAUDE.md` §7 与 `workspace.mdc` §4 把它列为共用，两侧升到 workspace-v19。Codex 只有在 `/stocks` 启动时才读得到根目录这份，子仓库和 `~/agent-work` 下靠用户级 `~/.codex/AGENTS.md` 指针（W-35）
- **下一步**：没有（Owner 10-10 签收）。根目录白名单（S0-3 `workspace.yaml`、S0-6 `check_workspace_root.py`）建的时候把 `AGENTS.md` 列进去
- **验收**：根目录 `AGENTS.md` 是指向 `bifrost-trade-infra/agent-config/AGENTS.md` 的链接；`bash scripts/check-agent-config-parity.sh` 通过；Codex 在 `/stocks` 下的提示输入里出现这份文件
- **验收结果**：PASS 2026-10-10 3542d24（parity 通过、两侧各 20 条；故意把一侧留在 v18 时报版本漂移；`codex debug prompt-input` 在 `/stocks` 下含这份文件；Codex 在 worktree 里经指针读到 `CLAUDE.md` §3 并用中文回答）
- **关联**：`agent-config/work/multi-agent/STEP0-PLAN-2026-10-08.md` 0.3 节、W-31

### W-35

**W-31 第 0 步 · S0-15 Codex 最低护栏**

- **类别**：道
- **状态**：已验收
- **现在**：
  - PATH 链接 `~/.local/bin/codex`；`~/.codex/hooks.json` 的 `PreToolUse` 经薄适配 `scripts/agent-guard/codex-pretooluse.js` 接 `preflight.js`（apply_patch 按文件拆成 Write，否则 D10 路径规则看不到它）；
  - hook 已 trust（`hooks/list` 拿哈希写进 `config.toml`）；沙箱 `workspace-write`、审批 `on-request`；受信任 `/stocks` 与 `~/agent-work`；`~/.codex/AGENTS.md` 指针；
  - `check-codex-guard.py` 查 trust 与配置，`check-agent-config-parity.sh` 在本机装了 codex 时跑它。内容与安装方法在 `agent-config/codex/README.md`
- **下一步**：没有（Owner 10-10 签收）。W-36 已改 hooks.json 命令、重新 trust，`--probe` 10-10 通过
- **验收**：Codex 执行 `git add -A` 被 preflight 拦下，执行允许的命令照常通过；`~/.codex` 的内容和安装方法写进 agent-config 文档
- **验收结果**：PASS 2026-10-10 ab93edb（不带 bypass、用 config 默认值：`git add -A` 被拦、暂存区 0；`git status` 通过；apply_patch 写 daemon-observe-safe 被 D10 拦；写普通文件通过；trust 之前同一条 `git add -A` 没经过 preflight。`test-codex.js` 9 条、`test.js` 136 条通过）
- **关联**：`agent-config/work/multi-agent/STEP0-PLAN-2026-10-08.md` 0.3 节、W-31、W-34

### W-36

**W-31 第 0 步 · S0-1 治理层可移植（含 D-1、D-4、D-6）**

- **类别**：道
- **状态**：已验收
- **现在**：
  - 工作区根统一读 `BIFROST_WORKSPACE`，没设就往上找 `bifrost-platform/config/ops-context.yaml`，找不到报错退出；旧名 `GIT_WORKSPACE_ROOT`、`BIFROST_WORKSPACE_ROOT` 仍读（AGENT_FACTS §6）；
  - Claude：hooks 用 `$CLAUDE_PROJECT_DIR`，`bifrost-analytics` 的 deny 并成一条项目相对的 `Edit(/bifrost-analytics/**)`（实测 `Write(...)` 那条从来不生效）；`.mcp.json` 用 `${BIFROST_WORKSPACE:-.}`；
  - D-1：Cursor 模板改 `${workspaceFolder}`、每个 server 钉 `PLATFORM_TOKEN_ENV_KEY`，`cursor/install-mcp.py` 渲染进 `~/.cursor/mcp.json`（已装，备份 `mcp.json.bak-20261010T021240`）；
  - D-4：infra（skills、README、autoMode payload 改占位符 `@WORKSPACE@`）、platform（git-bridge、code health）、research（pine lint 测试）、frontend（monitoring-ui 两侧，parity-id v3）；
  - D-6：platform 里 4 份退役 plist 已删；ConfigMap 记为 TD-290（集群写，要建单）；
  - Codex：`~/.codex/hooks.json` 命令改成 `"${BIFROST_WORKSPACE:-$HOME/Desktop/stocks}/..."`，重新 trust；`check-codex-guard.py` 现在用这条命令真跑一次 deny / allow；
  - 防线：`check_hardcoded_paths.py` + 基线（剩 Mac Mini 的 4 个文件、16 处）+ 8 个测试，`make check-hardcoded-paths`，登记 RATCHETS
- **下一步**：没有（Owner 10-10 签收）。同日定卡 7（路径棘轮接进 parity，只拦新增，infra 本批已接）、卡 8（删 platform `config/cursor-mcp-bridges.json`，只留 infra `cursor/mcp.servers.json`，platform `3dad199`）、卡 9（Codex hooks 默认路径留到 S0-3 bootstrap 统一写）。autoMode payload 在本机渲染结果与现行规则逐字相同，不重新 apply 也不影响本机；换机器时再跑两个 apply 脚本。platform 共享 checkout 因别的会话未提交的 `Makefile` 没能快进（git-bridge 仍跑旧代码，路径结果相同）；10-10 已解除：那份 Makefile 改动已提交为 platform `7cda6cb`，共享 checkout 在 main 上（STEP0-PLAN 0.9 第 4 条）
- **验收**：在另一个目录或账户下，preflight 能拦下探针命令；MCP 能起来；`check_hardcoded_paths.py` 只减不增
- **验收结果**：PASS 2026-10-10 4f39935（`/tmp/ws2` 另建工作区：`$CLAUDE_PROJECT_DIR` 的 preflight 拦下 `git add -A`、暂存区 0，8 个 MCP server 全部连上、`platform_mcp_health` 返回 PROD VIP；本会话 Cursor 重载后 `platform_mcp_health` 返回 `http://192.168.10.100:30876`、`get_auth_capabilities` 为 operator；`codex exec` 实测 `git add -A` 被拦、`git status --short` exit 0，`check-codex-guard.py --probe` 通过；`check_hardcoded_paths.py --ref origin/main` 在基线上（11 个仓库）；`check_mcp_cutover.py` 与 `--self-test`、`test.js` 136 条、`test-codex.js` 9 条、parity 通过；platform `go test ./...`、git-bridge 15 条、pine lint 4 条通过）
- **关联**：STEP0-PLAN 第 3 节 S0-1、0.3 节；提交 infra 4f39935、platform 75be701、research ecdce43、frontend 809d5579；TD-290

### W-37

**W-31 第 0 步 · S0-0 批准后由系统执行（先写方案）**

- **类别**：道
- **状态**：搁置（2026-10-12 15:26：这是个总条目，自己没有活。五个子项里 W-48、W-49、W-51 已上线，W-50 已搁置，W-52 已后移；页面此前一直把它算作「在做」）。之前：在做（方案已定，实现等 W-42）
- **估算**：进度 2/5 片 · 我还要 0 片 · 你还要 0 次 · 卡在 无 · 把握 高；它是总条目，自己没有剩余工作：五个子项里 W-48、W-49 已上线，W-50、W-51、W-52 做完它就关（2026-10-11）
- **现在**：方案已交（infra `9f9c3a1`，`work/multi-agent/S0-0-approved-execution-PLAN-2026-10-10.md`）；Owner 10-10 按推荐定了执行卡 1–7（全部选 A）。实现拆成 S0-0a–e，分给 W-48–W-52；TD-267、TD-276、TD-286、TD-287 归这几条
- **下一步**：W-42 合 main 之后开 W-48（S0-0a）
- **验收**：Owner 批一张 `owner_run_command`，系统自己执行并回写结果；通知里能看懂批的是什么
- **关联**：STEP0-PLAN 第 0 节 S0-0、0.3 节；W-48–W-52；TD-267、TD-276、TD-286、TD-287

### W-38

**W-31 第 0 步 · S0-14 节点非计划重启告警**

- **类别**：道
- **状态**：观察中（到 10-17，看有没有误报；2026-10-10 10:50 CDT 部署，`appr_6526224f3ef89e6d`，Prometheus 已加载规则组。送达演练还没做）
- **现在**：Owner 10-10 定：只新增告警规则作为一条新防线，TD-288 条目在 11-09 前不动
- **下一步**：已推 main（`c5c5f36`）；部署单由 Claude 线程代建（`plan_manifest` + C 级 `apply_manifest`），生效后由参谋长做送达演练。W-38 发现 main 上本来就红的两项静态检查，W-31 线程 10-10 已修并加了 pre-commit 防线（见 STEP0-PLAN 0.4 节）
- **验收**：用演练数据触发一次，告警能送到；登记进 MAINTAINERS
- **关联**：STEP0-PLAN 第 0 节 S0-14、TD-288

### W-39

**W-31 第 0 步 · S0-2 编号规则**

- **类别**：道
- **状态**：未开始（排到第 0 步之后：不在第 0 步「做完的标准」那六条里。统筹方 2026-10-12 10:20 定——Owner 当天说每一步具体做什么由统筹方按经验和教训判断，他只确认执行和计划有没有出入；要提前就说「W-n 提前」）
- **估算**：进度 0/1 片 · 我还要 1 片 · 你还要 0 次 · 卡在 我 · 把握 高（2026-10-11）
- **现在**：WORK.md 里只剩 `LANE-C` 一个别名要去；`LANE-A2` 直接进作废名单（0.1 节 D-18）
- **下一步**：照第 1 波计划派
- **验收**：`check_work_ids.py` 自测通过，对当前 WORK.md 跑一遍为 0
- **关联**：STEP0-PLAN 第 3 节 S0-2

### W-40

**W-31 第 0 步 · S0-7 D1 过渡层**

- **类别**：道
- **状态**：未开始（排到第 0 步之后：不在第 0 步「做完的标准」那六条里。统筹方 2026-10-12 10:20 定——Owner 当天说每一步具体做什么由统筹方按经验和教训判断，他只确认执行和计划有没有出入；要提前就说「W-n 提前」）
- **估算**：进度 0/2 片 · 我还要 2 片 · 你还要 1 次 · 卡在 我 · 把握 中；旧分支落后主线很多，rebase 的量没量过。你那一次：发版单（2026-10-11）
- **现在**：`cursor/d1-platform` 落后 main 41 个提交，冲突 4 个文件；第 1 波只做代码 rebase。S0-7 还要把 decide / sign-off 接进 `NeedsYouPage` / `useNeedsYou` 的计数，并做等待 7 天黄、14 天红（W-44 留的位）
- **下一步**：照第 1 波计划派
- **验收**：④ 能看到待你定的事和等待天数；⑦ 能看到 W-n 的状态
- **关联**：STEP0-PLAN 第 3 节 S0-7、W-4

### W-41

**W-31 第 0 步 · S0-4a Gitea 先备份**

- **类别**：道
- **状态**：未开始
- **估算**：进度 0/1 片 · 我还要 1 片 · 你还要 2 次 · 卡在 我 · 把握 中；你那两次：批 CronJob 的应用、看一次恢复演练的结果（2026-10-11）
- **现在**：只新增 CronJob，apply 要 Owner 批
- **下一步**：照第 1 波计划派
- **验收**：恢复出来的实例能 clone 到所有仓库
- **关联**：STEP0-PLAN 第 3 节 S0-4a

### W-42

**W-31 第 0 步 · S0-8 发版策略合并并签发**

- **类别**：道
- **状态**：观察中（集群部分 2026-10-10 到位：两个 ConfigMap、Role、Task 的 freeze 步骤，`appr_214783078f89d173` 和 `appr_b51a874cd805c18a`；接口随 platform `11ebb8c` 上 PROD。冻结步骤要等下一次 research 或插件发布才看得到真实输出。还差 Owner 的签名密钥、签第一份策略、冻结演练；策略里暂不含 PROD 流水线和增量 DDL）
- **现在**：卡 2 = B 落地：平台是唯一裁判，`release.sh` 只签名和调平台，infra 只留 ConfigMap、RBAC 和 Tekton 冻结检查。自定的 9 条决策、新接口和 Owner 待办记在 STEP0-PLAN 0.6 节；引出 TD-293、TD-294、TD-295
- **下一步**：Owner 生成 `~/.ssh/bifrost_release_owner` 并交指纹 → 线程写 `api/internal/releasepolicy/anchor.go` 推 main，随第 9 步上 PROD → Claude 线程 apply `configmaps.yaml`、`rbac-release-window.yaml`，再 `task-release-window.yaml` → `release.sh policy sign` + `status` → 三项演练
- **验收**：STG 影子检查审计记 covered；一次 PROD 发布自动批准并记下命中条款；冻结后 `start_pipeline_run` 返回 409、解冻后恢复
- **关联**：STEP0-PLAN 第 3 节 S0-8、0.3 节、0.6 节；TD-293、TD-294、TD-295

### W-43

**W-31 第 0 步 · S0-16 Console 清理 A（16a 零引用的死代码 · 16b 孤儿）**

- **类别**：道
- **状态**：观察中（到 10-12，看 PROD Console 有没有报错或缺功能；2026-10-10 11:30 CDT 上 PROD：run `bifrost-deliver-platform-prod-1791649613`，platform `11ebb8c`，ui `9b635b2`）
- **现在**：Owner 10-10 拆成两步（STEP0-PLAN 0.4 节）：W-43a 只删零引用的死代码，已派出（分支 `w31/w43a-s0-16a`）；W-43b 删孤儿，排在 W-44、W-45 之后。`AgentFocusDock`、`AgentTriadStrip`、`CommandIntentStrip`、`lib/task-mode`、`operateQueue` / `operateBriefs`、`lib/agent/*` 仍在渲染，不属于 16a；`NavAgentAskSlot` 改归 W-44。退役 plist 只在 W-36 删一次。W-43a 已并进 Console 集成分支 `w31/console-int`（platform `58928a3`，10-10）
- **下一步**：W-43b 已交付（`w31/w43b-s0-16b` `7299084`，参谋长 10-10 验收），删了无入口的 Control Room 四个分区、从未显示的 View agent 链接、SSH 控制台后端（三条路由现返回 404）和 xterm 依赖；清单在 `work/multi-agent/STEP9-REMOVED-UI-2026-10-10.md` 第 5 节。等第 9 步 STG 过目；进 main 后 infra `OVERSIZED_PLATFORM_BASELINE` 13 → 12
- **验收**：tsc / lint / vitest / build 全过，没有新的引用断裂
- **关联**：STEP0-PLAN 0.2 节

### W-44

**W-31 第 0 步 · S0-17 外壳与「需要你」第一版**

- **类别**：道
- **状态**：观察中（到 10-12，看 PROD Console 有没有报错或缺功能；2026-10-10 11:30 CDT 上 PROD：run `bifrost-deliver-platform-prod-1791649613`，platform `11ebb8c`，ui `9b635b2`）
- **现在**：范围见 STEP0-PLAN 0.2 节，按 0.4 节的卡 A、卡 B、卡 C 改：首页只列单子，批准和驳回只在 `#approvals?id=`；「需要你」只算待定、待批、待签；Autopilot 页签原样搬进「记录」。文件清单加 `lib/shell/shellStatusLine.ts`、`ConsoleSidebar.tsx`、`ConsoleNavSlotItem.tsx`、`StatusPage.tsx`，`NavAgentAskSlot` 也归这里
- **下一步**：已交付分支 `w31/w44-s0-17` `86b709f`（参谋长与 W-45 试合无冲突：tsc、lint 0 error、vitest 101 个文件 684 条、build 全过；needs-you 页没有批准 / 驳回按钮）。12 条自定决策登记在 STEP0-PLAN 0.5 节；W-43b 线程把它合进 `w31/console-int`
- **验收**：有待批的单子时首页第一屏就是它并显示等了多久；页头和 ① 的结论一致；通知里的旧链接仍能打开对应的单子
- **关联**：STEP0-PLAN 0.2 节、W-40

### W-45

**W-31 第 0 步 · S0-18 ⑤ Releases 三段式**

- **类别**：道
- **状态**：观察中（到 10-12，看 PROD Console 有没有报错或缺功能；2026-10-10 11:30 CDT 上 PROD：run `bifrost-deliver-platform-prod-1791649613`，platform `11ebb8c`，ui `9b635b2`）
- **现在**：Owner 10-10 定卡 B：第一段放快到期的策略和待批的发版单；失败的 run 放「进行中」，同一流水线、同一环境后来成功就自动进历史，不新增状态、不加接口。策略那一块等 W-42
- **下一步**：已交付分支 `w31/w45-s0-18` `611cc3e`（参谋长重跑：tsc、build、vitest 99 个文件 657 条全过）。7 条自定决策和 W-42 合并后的接入点登记在 STEP0-PLAN 0.5 节；W-43b 线程把它合进 `w31/console-int`
- **验收**：10-03 的旧失败不再占首屏；窗口被占用时看得到是谁在占、还剩多久
- **关联**：STEP0-PLAN 0.2 节、W-42

### W-46

**W-31 第 0 步 · S0-19 Console 清理 B（还在渲染的遗留）**

- **类别**：道
- **状态**：观察中（到 10-12，看 PROD Console 有没有报错或缺功能；2026-10-10 11:30 CDT 上 PROD：run `bifrost-deliver-platform-prod-1791649613`，platform `11ebb8c`，ui `9b635b2`）
- **现在**：已派出（分支 `w31/w46-s0-19`）；范围见 STEP0-PLAN 0.2 节。Autopilot 页签按卡 C 原样搬进「记录」（W-44），本道不删。10-10 已并进 `w31/console-int`（platform `58928a3`）；它删掉的 agent pack 带走了 TD-245 那条防线（RATCHETS 已写明理由）
- **下一步**：集成分支整体验收后合 main（不在本批）
- **验收**：⑥ 不再因为退役的 Agent 概念显示 NEEDS FIX；② 的备份面板不再报错
- **关联**：STEP0-PLAN 0.2 节

### W-47

**W-31 第 0 步 · S0-20 给 Design 的 ASK**

- **类别**：道
- **状态**：搁置（2026-10-12 15:26：不在这一轮。文档早已派出，之后没有人接着做；要用时先核对现状，再由 Owner 上传给 Design）。之前：在做
- **估算**：进度 0/1 片 · 我还要 0.5 片 · 你还要 1 次 · 卡在 我 · 把握 低；文档已派出，我还没核对现状；你那一次是把它上传给 Design（2026-10-11）
- **现在**：已派出；只写文档，由 Owner 搬运
- **下一步**：随时可以做
- **验收**：Owner 能直接上传
- **关联**：STEP0-PLAN 0.2 节

### W-48

**W-31 第 0 步 · S0-0a 状态机与编号**

- **类别**：道
- **状态**：观察中（到 10-17）：2026-10-10 13:50 上 PROD；第一次完整的 D 级执行是 #3（14:22）。后续 ①–⑥ 见下；其中「结果未知由 Owner 收尾」已做完，在 STG（`eb49c19`），等 PROD
- **现在**：新状态 `approved` / `running` / `unknown`、`execution{}`、全局自增 `#n`、`executor` 角色和领单 / 续租 / 回写接口、存储改 `statefile.Update`；TD-267、TD-276；`number` / `env` / `summary` / `deliveries` 接进 W-44 的列表行和详情页，替换临时的 `approvalEnv`
- **下一步**：第 9 步发完后按 0.8 节的顺序合 main（platform 与 infra 同批），合时把新状态、`executor` 角色与 `#n` 写进 `AGENT_FACTS.md`；`number` / `env` 接 Console 的部分等集成分支合 main（STEP0-PLAN 0.7 节第 6 步）之后
- **上线（2026-10-10 13:50 CDT）**：随整批发到 PROD（run `bifrost-deliver-platform-prod-1791658000`，platform `e5a0703`）。PROD 原有 31 条记录在新版第一次真实写入后 0 丢失、0 变化；新单从 #1 编号；#1 走完了「批准 → 认领 → 执行 → 记结果」（34 毫秒）。**上线后发现三件小事**：① 没有「演练单」：通知送达测试只能建一张真动作的单，#1（`trigger_cnpg_backup`，理由里写了测试单）19 秒后在 Console 被批准并执行，多做了一次全量备份；需要一个不执行任何东西的演练动作，以及建单方撤回自己待批单的能力。② 一次执行在审计里记了两行 `approval.execute`（actor=platform 和 actor=admin）。③ 零值时间被写进记录（待批单的 `decided_at`、`claim_expires_at`、`next_attempt_at`、`lease_expires_at` 是 `0001-01-01`）。④ 第一次真实的 D 级执行失败（#2，14:16）：执行脚本只认纯十六进制的租约编号，平台发的是 `lease_` 加十六进制；平台已认领，命令没开始。已修（infra `57cf673`），重建为 #3。脚本的测试夹具是自己编的；要加一个让脚本打真实 Go handler 的契约测试并放进 CI。⑤ 「结果未知」的单子没有收尾入口（`unknown` 算未结，永远留在 Needs you）：需要一个 Owner 用的收尾动作（没有执行 / 已执行成功 / 已执行失败，带说明），是新接口，等 Owner 定；脚本在认领成功但随后自己拒绝时，应把单子退回 approved。⑥ 发布上去的 `e5a0703` 在 CI 上是红的（`ci-platform-wzt8x`）：`TestAgentThreadsRoutesAuth` 在集群 Pod 里失败（测试没有把状态后端固定成文件），代码健康超过 800 行的文件 15 个对基线 12（新增 `agentthreads/threads.go` 971、`agentthreads/threads_test.go` 1167、`approvals/execution.go` 816）。修测试、拆这三个文件；CI 变绿前不再发平台。⑦ 「结果未知」的页面让 Owner 无从判断（2026-10-11，#2）：要补三样：建单的线程可以给一张未知的单附上「建议的结论 + 证据」（不生效，只供 Owner 确认）；未知状态下不显示「批准后在终端运行」那一块；同一条命令的前后几张单互相指到
- **验收**：方案第 4.5 节 S0-0a 的验收命令；暂时性拒绝后单子仍是 `approved`，两个并发建单拿到不同的 `#n`
- **关联**：`work/multi-agent/S0-0-approved-execution-PLAN-2026-10-10.md` 第 4.5 节；W-37；TD-267、TD-276

### W-49

**W-31 第 0 步 · S0-0b 通知文案与投递记录**

- **类别**：道
- **状态**：观察中（到 10-17）：2026-10-10 13:50 上 PROD；当天 5 条推送都被中转接收，Owner 确认手机收到。标题改成以动词开头（Decide / Check / Look）已做完，在 STG，等 PROD
- **现在**：文案带 `#n`、级别、动作、环境、摘要；`deliveries[]`；结果通知与过期提醒；TD-286；relay 错误里的 ntfy topic 已掩码（TD-296）
- **下一步**：W-48 合 main 后合；发 STG 后做上面的实测。发版策略到期提醒的投递记录是 S0-0b 遗留（0.8 节）
- **验收**：STG 上建一张 C 级单：手机通知显示 `#n`、动作、环境，单子的 `deliveries[0].result` 是 `accepted`
- **关联**：`work/multi-agent/S0-0-approved-execution-PLAN-2026-10-10.md` 第 4.5 节；W-37；TD-286

### W-50

**W-31 第 0 步 · S0-0c 带外执行器**

- **类别**：道
- **状态**：搁置（随 W-56 的全自动部分，2026-10-12）。之前：未开始（等 W-42 合 main）
- **估算**：进度 0/3 片 · 我还要 3 片 · 你还要 3 次 · 卡在 我 · 把握 低；牵涉两台 Mini 重新部署和专用凭证。你那几次：放凭证、换 ntfy topic、批一次演练（2026-10-11）
- **现在**：operator-plane 在 .50 以执行者角色领单（执行卡 1 = A），只放专用受限凭证（执行卡 2 = A）；输出只回写退出码、用时、哈希和 ≤2 KB 打码尾部，全文留 .50 30 天（执行卡 6 = A）；TD-287；TD-290 的删除做演练；TD-291 的两台 Mini 重新部署并入这里；TD-296：重新部署 .50 operator-plane，准备时 Owner 换 ntfy topic。不做 D 级权限框的截断显示（Owner 10-10 推翻，D 级只在 Console 批，STEP0-PLAN 0.9 第 2 条）
- **下一步**：W-42 合 main 之后照方案第 4.4 节的顺序开
- **追加（2026-10-10）**：Owner 把 PROD Console 开在 Claude 应用自带的浏览器面板里，并在那里保存了审批令牌；这个面板 Agent 的浏览器工具能操作（闸门禁止 Agent 去点审批页，靠的是规则，不是隔离）。带外执行器和签名密钥落地时，批准用的凭证要放在 Agent 的任何工具都够不到的地方；在那之前建议 Owner 只在自己的浏览器或手机上批，并轮换这次露出的令牌
- **验收**：Owner 只点一次批准，TD-290 的 ConfigMap 由系统删掉，单子 `executed`、退出码 0；`get_agent_bridge` 的 `git_bridge` 是 `not_configured`
- **关联**：`work/multi-agent/S0-0-approved-execution-PLAN-2026-10-10.md` 第 4.5 节；W-37；TD-287、TD-290、TD-291

### W-51

**W-31 第 0 步 · S0-0d 会话「批 #n」**

- **类别**：道
- **状态**：观察中（到实测为止）：代码在 PROD。2026-10-11 14:20 核对：platform `w31/w51-s0-0d` `54e0cfb` 和 infra 的用法文档 `5932186` 都已是主线的祖先（10-10 随集成分支 `w31/s0-0-int` 合入），PROD 跑的 `6524330` 包含它。台账此前一直写「待合并」，是没更新。还差验收里的实测：在一个新开的 Claude 线程里对一张真实的待批单说「批 #n」
- **估算**：进度 2/2 片 · 我还要 0 片 · 你还要 1 次 · 卡在 你（下一张发布单出来时在新线程里说一次「批 #n」） · 把握 中；代码已上线，没实测过。你那一次不另占发版单，用下一张就行（2026-10-11）
- **现在**：`approve_request` / `reject_request` 收 `#n` 加 `approval_line`，与记录重算的一行相等才发；D 级「批 / 驳 #n」一律不发请求、返回 Console 链接，级别以服务端记录的 tier 为准；`list_pending` 返回 `approval_line`，D 级只给链接；没有 bifrost-approve 的会话拿到 `approve_hint`
- **下一步**：W-49 合 main 后合 platform `54e0cfb`，再合 infra 文档 `5932186`；PROD 上线后通知决策线程实测（决策线程先重启拿新 MCP）
- **实测（2026-10-11 10:56）**：Owner 在线程里说批 #7，统筹线程用现在线上的 `approve_request`（只带 id 的旧版）提交，PROD 回 409 `approval_line and params_hash do not match`——服务端已经要求带上审批行和参数哈希，旧工具不带。也就是说在这一条上线之前，会话里批在 PROD 上不可用，只能在 Console 上批。没有绕开（不直接调接口、不碰管理员令牌）。 **14:20 更正**：这次 409 不说明「这一条没上线」。服务端要求带审批行，正是这一条上线后的行为；不带的是统筹线程自己那个 10-10 13:40 启动的旧 MCP 进程。我当时没有去看分支是不是主线的祖先，就写了「没上线」，并把它写进了 OWNER-SURFACE 的 C1 和 P2（已更正）。
- **验收**：Claude 会话里打「批 #n」：弹出允许，批准后单子的 `channel` 是 `chat`；对 D 级单说「批 #n」只给 Console 链接、单子保持 pending；服务端对 D 级 `channel=chat` 批准返回 403
- **关联**：`work/multi-agent/S0-0-approved-execution-PLAN-2026-10-10.md` 第 4.5 节；W-37；—

### W-52

**W-31 第 0 步 · S0-0e 网页推送**

- **类别**：道
- **状态**：未开始（排到第 0 步之后：不在第 0 步「做完的标准」那六条里。统筹方 2026-10-12 10:20 定——Owner 当天说每一步具体做什么由统筹方按经验和教训判断，他只确认执行和计划有没有出入；要提前就说「W-n 提前」）（等 W-42 合 main）
- **估算**：进度 0/2 片 · 我还要 2 片 · 你还要 2 次 · 卡在 我 · 把握 中；依赖 HTTPS。你那两次：发版单、在 iPhone 上装主屏幕应用并订阅（2026-10-11）
- **现在**：`webpush-go`（执行卡 5 = A，开工前核实维护情况和遥测），订阅存在现有状态文件新开的 `push-subscriptions` 键（执行卡 7 = A）；ntfy 只留严重告警。挂进 W-44 已放的 PWA 骨架 `console/public/sw.js`，依赖 HTTPS（只在 HTTPS 下生效）
- **下一步**：W-42 合 main 之后照方案第 4.4 节的顺序开
- **验收**：Owner 的 iPhone 主屏幕应用收到 `#n` 推送，点开到 `#approvals?id=`
- **关联**：`work/multi-agent/S0-0-approved-execution-PLAN-2026-10-10.md` 第 4.5 节；W-37；—

### W-53

**VPN → Ops 防火墙放行与网络审计覆盖**

- **类别**：道
- **状态**：观察中（到 10-12；规则 2026-10-10 生效，Owner 确认手机走蜂窝能用；审计期望数 11 随 platform `11ebb8c` 上 PROD 后实测 `POLICY_NOMINAL`、`expected_policy_count` 11。后续三项见「下一步」）
- **现在**：规则已在网关上并生效（2026-10-10）。platform `f995b00` 在基线里加了 `Bifrost | ALLOW VPN → Ops VIP`（源 VPN 区 `192.168.2.0/24`，目的 `192.168.10.100` TCP 443，带回程）；Owner 批准 `appr_d30b18c951439d55` 并运行，输出 exit=0，只新建这一条。从 `/api/v1/network/policies` 读回：正向与回程两条都在，网关策略 183 → 185。Owner 确认手机走蜂窝能用 Ops。原因：`Bifrost Server` 是自定义区，VPN 区默认被拒，基线里原先没有放行
- **下一步**：① `unifi_firewall_apply` 在 PROD 跑不了：镜像是只装了 Go 程序的 alpine，没有 python 和 `scripts/`（读代码与 `k8s/cicd/docker/Dockerfile.platform-api-stg` 得出，没有实跑）；把基线和创建规则移进 Go，或给镜像带上执行器。② 审计只核对规则名和 5 个区的绑定：补 VPN 区、各区之间的默认动作、VPN 客户端；`/api/v1/network/policies` 只返回 `Bifrost |` 前缀的规则。③ 审计期望数 11 随 platform 下次发版生效，不为这一条单独发版。④ 守卫拦下所有提到 `scripts/unifi_*` 文件名的 shell 命令，包括 `git commit` 的路径参数；是否像 TD-278 那一组一样只拦运行，由 Owner 定
- **验收**：手机关 Wi-Fi 走蜂窝、不手动连 VPN，能打开 `https://ops.bifrost.lan`；回到家里 Wi-Fi 后 VPN 断开，Ops 仍能打开；platform 仓库 `python3 scripts/unifi_firewall_policy_test.py` 通过；platform 发版后 `GET /api/v1/network/audit` 为 `POLICY_NOMINAL` 且 `expected_policy_count` 为 11
- **关联**：platform `f995b00`；`work/multi-agent/DESIGN-agent-runtime-2026-10-08.md` 第 19 节；W-37；W-44

### W-54

**W-31 第 0 步 · S0-21 线程心跳与静默告警**

- **类别**：道
- **状态**：观察中（到 10-17，看有没有误报）：2026-10-11 21:08 观察期内的一条误报：Codex 的后台实现运行超过 10 分钟，被列成静默线程并出现在 Owner 的「Needs you」里，而进程活着、日志在写（原因和修法见 TD-316，教训第 96 行）。之前：2026-10-10 13:50 上 PROD，13:55 钩子接上，14:08 验收（模拟线程 10 分 26 秒后被发现并推送），14:22 两条告警规则装上
- **现在**：platform `w31/w54-s0-21` `c854efe`（`api/internal/agentthreads/`：`POST /api/v1/agent/threads/heartbeat` 用 reporter 及以上令牌，`GET /api/v1/agent/threads` viewer 级（无令牌或未知令牌 401），workers 每 30 秒巡检、每次静默只推一条）；platform `w31/w54-s0-21-console` `7b4574d`（已并入 console-int `11ebb8c`，合并提交 `167c1ea`；Status 页 In progress · Agent threads，静默计入 Needs You；用 viewer 凭据读，与审批列表共用 `approvals.ts` 导出的 `viewerRead`）；infra `w31/w54-s0-21` `5560144`（三家共用的 `agent-config/scripts/thread-heartbeat.js`、维护项 `agent-thread-watch`、告警 `BifrostMaintainerAgentThreadWatchStale` 与规则测试）。验收 5 条的单测全过
- **下一步**：① 合 main 前改 viewer 级：已完成（`c854efe`、`7b4574d`）。② 合 main：infra 先（规则 plan / apply `k8s/monitoring`），合入后重跑 `python3 bifrost-trade-infra/agent-config/cursor/install-hooks.py` 把心跳 hooks 装进 `~/.cursor/hooks.json`（TD-298）；再 platform `w31/w54-s0-21` 上 PROD；console 分支等第 9 步之后，合并时留意 `console/src/api/approvals.ts` 的 `viewerRead` 导出。③ 部署后真机验收，另验三件未证实的事（STEP0-PLAN 0.9 节）
- **验收**：0.9 节的 5 条（单测已过，真机待部署）
- **关联**：W-31；W-44（① 的「进行中」）；ADR §12.9 第 9 条；TD-298

### W-55

**发版策略 · DDL 分类器重做成允许清单（Codex 审查 R01）**

- **类别**：道
- **状态**：已放弃这个做法（2026-10-10）：三轮修复，Codex 三次独立复核都判「不成立」，按第三轮前定下的止损线停止。`additive_ddl` 保持 `false`，分支 `w31/w55-ddl-allowlist`（`f2d8cda`）不合并
- **现在**：已复现：`ClassifyDDL` 按行匹配禁止词、默认放行，换行、注释夹在关键字中间、`DO` 块、`VACUUM FULL`、语句换序都被判成可自动放行（platform `7cda6cb`）。指纹还是空的，现在没有策略生效。止血已做：策略模板 `additive_ddl` 改成 `false`，测试断言它保持关闭
- **下一步**：① 小改动：平台引擎里去掉「增量 DDL 可以自动放行」这条分支，任何 DDL 命中都等 Owner，不再依赖模板里的开关（收紧）。② 替代方案只记方向，不开工：在只有结构的空库上执行，按目录差异判断；这个库的 DDL 大多写在 Python 里，自动执行的实际收益小，等 DDL 审批真的成了负担再由 Owner 定。三份复核报告在 `work/multi-agent/reviews/codex-2026-10-10-w55-round{1,2,3}.md`
- **验收**：`REVIEW-codex-2026-10-10-RESPONSE.md` R01 表里每一条危险输入都被拒绝，两条对照结果不变；`go test ./internal/releasepolicy/...` 通过；Codex 复核结论记在本条
- **关联**：W-42；`work/multi-agent/REVIEW-codex-2026-10-10.md` R01

### W-56

**无人值守 PROD 发布的门槛（Codex 审查 R02）**

- **类别**：道
- **状态**：在做（Owner 2026-10-12 12:30 定的方向：规则和护栏先做，协作机制搁置，用现在这套协作去做真实的工作，回头按实际运作再看。**只做护栏的部分**：流水线自己检查「该提交 CI 成功、STG 跑的是同一个提交」；按固定提交和镜像摘要部署（TD-295）；一天至多一张正式环境发布单。**全自动发布的部分搁置**：冻结协议第二片（Owner 的集群操作）及以后、策略改成只增的记录。停在：冻结检查第一片在主线上没接线；设计的修订（2026-10-12，922 行）复核 121「先修」，之二在改，收完归档即停，不再送复核；操作单和两份任务书在统筹方的工作目录里，没派。正式环境照旧拒绝冻结，每次发版由 Owner 批。恢复条件：发版频繁到「一天一张单」也嫌多。）之前：在做（冻结检查第一片 2026-10-12 00:08 过复核进了两个仓库的主线，没接线；下一步是第二片的任务书，在统筹方手里）。之前：2026-10-11 16:38：信任锚（TD-310 的后一半）按事先写下的条件停线，三次复核共找到六种不经新签名放行的办法；密钥不编进平台，PROD 上冻结继续被拒绝、没有东西自动批准。解冻协议先出设计（`work/multi-agent/DESIGN-release-freeze-protocol-2026-10-11.md`），见 `PLAN-w56` 决定记录之六。之前：在做（7 步里在第 1 步，第 1 步分 A–F 六片。B 片——每条有副作用的流水线先过故障即拒的冻结检查——2026-10-11 在仓库里做完，含兄弟仓库 flex-query 那条，还没应用到集群，应用要 Owner。A 片——量出谁能改 PROD——离线重算两轮、改成向 apiserver 提问后又三轮，都没过独立复核，08:12 按预算停线；Owner 10:55 说继续，同日重开（两轮预算），这一轮加一条从采集到重放贯通的测试，分支 `w31/w56-matrix`。方案 `work/multi-agent/PLAN-w56-unattended-prod-2026-10-10.md`，决定记录之一至之四）
- **估算**：进度 0/3 片 · 我还要 3 片 · 你还要 2 次 · 卡在 Claude · 把握 中；2026-10-11 18:10 更新：信任锚的实现停线后，解冻协议换了形状，设计两稿过了复核（片数不变：原来的 C、D 两片由它的 S1–S5 取代，仍按 12 片估，待第一片做完再重算）。你多出来三次：定 4 项决定（一句话）；两次亲手的集群操作（装新类型和准入规则；排空、写墓碑、收窄权限、打开开关并演练）。启用之前还要关掉 TD-314 和 TD-293 两条提权路。此前的说明：A 片（量出谁能改 PROD）2026-10-11 14:07 第三次停线：第 7 轮的复核 75 又找到一种「采集器不会发的请求被接受」，事先写下的停线条件成立，分支不合并。新方向是录制包由 Owner 的发布密钥签名、重放先验签，要先出设计并复核，排在签名密钥有了之后。B 片已装到集群，演练只过了一半；TD-310 统筹方的一半已进主线，等 Owner 生成密钥。后面六步每步按 1–2 片粗估。你那几次：生成发布签名密钥并重做冻结演练、跑带模拟身份的测量、应用收权的清单、签发版规则、第一次按规则放行时看一眼（2026-10-11）
- **现在**：策略能自动批准，但发布失败后的恢复还不成熟：platform 的 PROD 发布没钉 SHA（TD-295），镜像是可变标签、回滚要重建，冻结没有覆盖全部入口（TD-294）且平台账号能改冻结 ConfigMap（TD-293），自动回滚没实现
- **下一步**：出方案：每个入口遵守冻结、逐仓固定 SHA、按镜像摘要部署、保留上一版产物回滚不重建、独立的失败检测与回滚、platform 自身升级失败由带外操作面回滚。Owner 2026-10-10 已定：这些验收之前策略里不列两条 PROD 流水线（模板已改，测试守着）
- **追加（Owner 2026-10-11 夜，两条；只是需求，随冻结协议后面几片出设计）**：① 冻结和解冻在运营平台上是什么样。按下：Console 上要有一个「冻结发布」的按钮（平台账号有新建冻结记录的权限），旁边显示现在冻没冻、谁冻的、几点、原因，以及怎么解；设计目前只写了命令和平台动作，没有写页面。松开：按 D2、D4 不在 Console 上——由 Owner 在自己的终端用自己的集群凭证执行 `release.sh unfreeze`，平台账号对冻结记录只有建和读、没有删。后果要写明给他：不能在手机上解冻；想要手机上也能解，需要一个只在他设备上的专用身份，是另一份设计（D2 的「一句话推翻」）。② 定期演练。计划里只有上线前的一次（八步，他在场）；没有定期的。要有三层：每次提交跑代码层的用例（已有）；一个只读探针持续用真集群跑这道检查，没冻结时答不出「放行」就告警，冻结超过设定时长没解也提醒；真演练按期做——真的冻结、确认每个发布入口都被拒、由他解冻——并在动过这条路上的任何东西（代码、权限、准入策略、集群升级）之后加做一次。Console 显示上次演练的日期和下次到期，过期告警。统筹方的建议：头三个月每月一次，之后每季度一次，每次需要他约 10 分钟。
- **护栏 ② 的做法（统筹方 2026-10-12 16:56 定，留痕）**：检查放在流水线里（同步镜像之后、拉代码之前）：解析出一个提交；要求它有成功的 CI（和 `release.sh` 同一个判定）；要求测试环境最近一次成功的发布构建的是它；之后构建用的就是它；出错即拒。实现第一轮按任务书停下——流水线任务默认的身份 `cicd:default` 读不了 PipelineRun / TaskRun。三个办法：A 给 `default` 加读权限（要 Owner 改 RBAC，而且每个构建 Pod 都多了读权限）；B 让这个检查任务跑在 `tekton-deliver` 下——它已经有这几样读权限，平台本来就让 `rollout`、`gitops-sync` 跑在它下面，只要平台代码把新任务也列进去，**不改任何权限**；C 改成平台在执行审批时检查（只管得住经平台发起的发布）。**选 B**：不给任何人新权限，检查在流水线里，各种发起方式都过它；不是经平台发起的 run 会跑在 `default` 下，读不到就拒绝（出错即拒）。代价：平台要改一处并发一版，两处上线的先后要保证哪种次序都不打断发布（第二轮任务书要求实现者从 Tekton 的校验规则里查清）。推翻：「护栏 ② 改用 A」或「改用 C」。
- **护栏 ② 复核之后的裁定（统筹方 2026-10-12 17:45，留痕）**：独立复核 132（Claude 的子代理，`work/multi-agent/reviews/claude-2026-10-12-review132-…`）结论「先修」。属于哪一种：**没有**找到会放行错误提交、检查的和构建的不是同一个提交、或查询出错仍放行的路径；找到的是「正规的发布被误拒」一条（Owner 的钉住路径生成的 run 没给检查任务指定身份）和「最近一次」的定义在两次测试环境发布交叠时会认错一条，另有 6 条规则只缺测试。两半都还没接线（流水线没应用），所以没有任何发布受影响。按 Owner 13:24 的规矩（复核发现的由统筹方或 Codex 修），第 3 轮交 Codex 修，改完由统筹方跑测试和种错，再请同一位复核方确认。平台那一半复核没找到问题，已合进平台主线 `2726c47`。统筹方定的几处：① 「测试环境最近一次」改严——取创建时间最新的那一次，它必须是成功的，而且别的每一次都必须在它之前结束；最新的一次在跑、失败、或有更早的一次比它晚结束，都拒绝并点名。理由：这一条代表的是「测试环境现在跑的就是这个提交」，说不清的时候宁可拒。② 平台的 CI 只认 `bifrost-ci-platform` 的 run，并且只按标签读这两条流水线的 run，无关的 run 形状异常不再能挡发布。③ 检查任务的三个参数显式声明并传入。④ 不留「带红放行」：要越过只有 Owner 把流水线的旧定义重新应用。⑤ 应用之前先由 Owner 起一条只含这个检查的试跑（一正一反），它不拉代码、不构建；镜像里有没有 python3 和 git 也由这次试跑验证——平台的探针 Pod 不允许进 `cicd`、也不允许这个镜像，统筹方试过被拒，没有绕。⑥ 统筹方已用只读身份把脚本对着集群里的真对象跑过：主线提交通过，上一个主线提交和一个没有 CI 的分支提交被拒；列全部 run 0.7 秒、10 MB。推翻：「护栏 ② 的裁定撤回」。
- **追加（Owner 2026-10-12 09:55，采纳等待规矩时）**：发版只有卡住的时候才应该来找他，没卡住的应当自动，今后会经常发版。统筹方的记录：这和 2026-10-10 定的方向一致，是本条目的目标；今天正式环境每一次发版仍要他批（发布策略里不列两条正式环境流水线，他 10-10 定的，验收过之前不变）。做完之后找他的只剩三种：改动在策略之外、检查没过或卡住、冻结期间。在那之前统筹方把同一仓库一天的改动攒成一版，一天至多一张正式环境发布单（`RULE-waits-2026-10-12.md` 第 6 节）。
- **优先级（Owner 2026-10-10 晚）**：Owner 批完当天第二次 PROD 发布后说，他现在批的主要是「批准发布」，这是架构要解决的核心痛点，目标是自动发布、事后校验。排在 W-61、W-62 的界面几片之后的第一位。其中两条可以先做，Owner 仍在逐个批的时候也能先堵住当天这类风险：① 平台的发布流水线自己检查「该提交的 CI 成功，且 STG 上跑的是同一个提交」（当天在 CI 红的情况下发了 PROD，LESSONS 第 38 行）；② 按镜像摘要部署 STG 验过的同一份产物。当天实测：Console 的构建是确定的（STG、PROD、本机三处同一个文件名 `index-w5udhj9Y.js`），api 镜像 PROD 是重新构建的（摘要不同）
- **验收**：演练：批准后分支前进、标签被改、两个发布并发、冻结期间各入口、新版 platform 起不来；部署身份不漂移，回滚不重建
- **关联**：W-42；TD-293；TD-294；TD-295；ADR §12.10 门槛表

### W-57

**W-31 第 0 步 · 宿主心跳与「未接入监测」（W-54 的后续，Codex 审查 R07）**

- **类别**：道
- **状态**：搁置（随 W-67，2026-10-12）。停在：代码在两个仓库的主线上，没在任何主机加载。之前：在做（2026-10-12 核对：代码已经在两个仓库的主线上——平台收主机心跳的路由 `api/internal/server/server.go:481`，infra 的 `agent-config/scripts/host-heartbeat.js`、launchd 模板和安装脚本；还没有在任何主机上加载，正式环境跑的是不是这一版没核对。此前台账写「未开始」是错的。并进 W-67 的主机守护进程最小版，设计 `work/multi-agent/DESIGN-host-minimal-2026-10-12.md`）
- **估算**：进度 0/2 片 · 我还要 2 片 · 你还要 2 次 · 卡在 我 · 把握 中；你那两次：发版单、每台主机装定时心跳时可能要你的权限（2026-10-11）
- **现在**：W-54 的规格自相矛盾：承诺 12 分钟内通知，阈值却是 max(10 分钟, 工具超时 + 2 分钟)；会话事件判断不了宿主睡眠；没配令牌的线程看不出来
- **下一步**：每台 Agent 主机加一个每分钟的定时心跳，和会话事件分开判断；没有令牌或钩子失败的线程显示「未接入监测」；规格里的时限改成：宿主失联 3 分钟内，会话静默按阈值公式另加推送延迟
- **验收**：W-54 的 5 条，再加：30 分钟工具超时下睡眠、超过 10 分钟的正常思考、无令牌或上报失败、父子会话并行、断网后事件迟到；分别记漏报、误报和送达时间
- **关联**：W-54；STEP0-PLAN 0.9、0.10 节

### W-58

**W-31 设计修订（Codex 审查 R03–R06、R08）**

- **类别**：道
- **状态**：未开始（排到第 0 步之后：不在第 0 步「做完的标准」那六条里。统筹方 2026-10-12 10:20 定——Owner 当天说每一步具体做什么由统筹方按经验和教训判断，他只确认执行和计划有没有出入；要提前就说「W-n 提前」）
- **估算**：进度 0/2 片 · 我还要 2 片 · 你还要 1 次 · 卡在 我 · 把握 中；写设计加复核。你那一次：Gitea 的库放哪里（2026-10-11）
- **现在**：审查指出五处契约没写全：修复链状态与 Gitea 的库、过期租约的执行者恢复、评审身份粒度、额度与硬预算、阶段退出条件和测试归属
- **下一步**：Claude 改 `DESIGN-agent-runtime-2026-10-08.md` 和第 0 步退出条件；R04 的租约、代次与隔离契约请 Codex 细化；Gitea 的库放哪里给 Owner 选项
- **验收**：ADR §12.10 门槛表每一行都能指到验收和证据；T04–T07、T16 有通过时点；状态机故障测试有隔离环境；`work/multi-agent/LESSONS-from-practice.md` 里每一行都有对应的运行时要求和测试，或写明接受的理由
- **关联**：W-31；`work/multi-agent/REVIEW-codex-2026-10-10-RESPONSE.md`

### W-59

**观测类清单变更随策略自动执行（规则放宽，Owner 2026-10-10 选 A）**

- **类别**：道
- **状态**：未开始（排到第 0 步之后：不在第 0 步「做完的标准」那六条里。统筹方 2026-10-12 10:20 定——Owner 当天说每一步具体做什么由统筹方按经验和教训判断，他只确认执行和计划有没有出入；要提前就说「W-n 提前」）
- **估算**：进度 0/2 片 · 我还要 2 片 · 你还要 2 次 · 卡在 我 · 把握 中；你那两次：签改过的策略模板、发版单（2026-10-11）
- **现在**：`apply_manifest` 的级别只看命名空间，`monitoring` 里加一条 warning 告警规则也要 Owner 批。Owner 选了提议里的 A：对象种类限 `PrometheusRule`、`ServiceMonitor`、`PodMonitor`、`ScrapeConfig` 和带 `grafana_dashboard` 标签的 `ConfigMap`；只在 `monitoring`；只新建或更新；不含 `severity: critical`；提交在 main 且 CI 通过；策略有效
- **下一步**：派 Cursor：platform 的 `classifyApply` 读 plan 摘要里的对象种类、动作和 severity，策略引擎加 `apply_observability` 条件；infra 的策略模板加这一条件。判断只用结构化结果，读不出来按 C 级。完成后交 Codex 复核
- **追加（2026-10-10 下午）**：`k8s/monitoring/bifrost-maintainer-rules.yaml` 的 plan 失败（`plan-7d96516a-1791658544`）：对象归 `kubectl-client-side-apply`，平台用 `--server-side --field-manager=bifrost-applier` 且不带 `--force-conflicts`，遇到字段归属冲突。当天第二次（第一次是 W-42 的 Task）。这次用一张 Owner 执行的单（#2）一次性把归属交给 `bifrost-applier`。规则落地时要包含：plan 发现冲突方只有 `kubectl-client-side-apply` 时，在 diff 里写明「将接管归属」，批准后带 `--force-conflicts` 应用；盘点 `k8s/monitoring` 下还有多少对象归手工 apply
- **验收**：提议里每一条排除项都有测试且仍是 C 级；一份只含 warning 级 `PrometheusRule` 的 plan 在策略有效时按 B 级执行、过期或冻结时回到 C 级；Codex 复核结论记在本条
- **关联**：`work/multi-agent/RULE-PROPOSAL-observability-apply-2026-10-10.md`；ADR §5；W-42；W-55

### W-60

**Tekton 运行记录的保留与清理（TD-299 的长期方案，Owner 2026-10-10 定起点值）**

- **类别**：道
- **状态**：未开始（排到第 0 步之后：不在第 0 步「做完的标准」那六条里。统筹方 2026-10-12 10:20 定——Owner 当天说每一步具体做什么由统筹方按经验和教训判断，他只确认执行和计划有没有出入；要提前就说「W-n 提前」）
- **估算**：进度 0/2 片 · 我还要 2 片 · 你还要 2 次 · 卡在 我 · 把握 中；之后还有一周观察。你那两次：批首次清理的清单、发版单（2026-10-11）
- **现在**：`cicd` 里留着 545 个 PipelineRun、3958 个 TaskRun（都是最近 7 天的，每天约 78 次运行），没有清理。控制器全量对账时新 run 等了 4 分 21 秒。发布证据已经另存：平台给每次完成的发布写一条发布记录（`bifrost.io/release-record` 标签的 ConfigMap，10-10 有 380 条），步骤日志由 promtail 收进 Loki（保留期还没核对）
- **下一步**：① 核对 Loki 里确实有 Tekton 步骤日志和它的保留期。② 派 Cursor：在 `api/internal/releases` 写发布记录的循环里加清理，规则是成功的留 24 小时、失败的留 7 天、每条流水线至少留最近 5 次、发布类必须已有发布记录才删；先只干跑并输出清单。③ Owner 批首次清理的清单，之后按规则自动。④ 加告警：TaskRun 数量超限，新 TaskRun 两分钟没有 Pod。⑤ 发布记录自己设上限告警，运行时的库建好后迁进去，之前旧的归档到 NAS
- **验收**：`kubectl -n cicd get taskrun --no-headers | wc -l` 连续一周低于定下的上限；控制器全量对账期间起的 plan 30 秒内拿到 Pod；被删的发布类运行都能在发布记录里查到
- **关联**：TD-299；ADR §7；W-56（发布记录要带镜像摘要）

### W-61

**Ops Console · Owner 事项的七个问题与手机处理闭环（Codex 研究并入，Owner 2026-10-10）**

- **类别**：道
- **状态**：观察中（到 10-17）：三片都在 PROD（2026-10-10 20:43 与 10-11 00:04）：详情页决定卡、待批列表、Needs you 分组与最近已处理、令牌不进 DOM、通知动词、结果未知由 Owner 收尾
- **现在**：Needs You 上的一条单子只有动作名、被截断的理由和编号，Owner 看不出为什么要他批、不批会怎样。手机上页头系统结论在 360 / 390 / 430 像素宽时只剩 33 / 63 / 103 像素，触控目标 20–28 像素，读取没有超时，读不到时可能显示成「没有待办」。依据在 `work/multi-agent/RESEARCH-codex-ops-console-owner-value-2026-10-10.md` 和 `RESEARCH-codex-ops-console-responsive-2026-10-10.md`
- **下一步**：① 后端：审批记录加「为什么是你」（定目标 / 定规则 / 不可逆 / 过渡期门槛及关联工作项）、「不回复会怎样」、「建议」三个字段，建单接口和 MCP 工具带上。② 前端第一段：页头两行（页名、环境在第一行，系统结论和更新时间在第二行并可换行）、触控目标 44 像素、读取状态（连接中、刷新中、连接丢失、数据可能已旧）。③ 前端第二段：Needs You 和审批详情按七个问题排版，Releases 在手机上改卡片。④ 监控页排版放最后
- **追加（Owner 2026-10-10 下午）**：Owner 指出本机进展看板上的逐步进展和 PROD 上的待批列表是两个地方、对不上。要求：PROD 上每一个待批项都挂在它所属的那件事的流程上，写明这是哪件事的第几步、批了之后发生什么和大约多久、之后轮到谁；演练或测试的项用单独的类型，页面和通知的标题里就标明，不带批准入口（当天 #1 测试单被批准执行就是反例）。设计在 DESIGN §20.2、§20.3 第 8 条
- **第一片在做（2026-10-10 14:13 派给 Cursor，分支 platform `w31/w61-approval-page`，任务书 `~/agent-work/w61-approval-page/TASK.md`）**：Owner 在 PROD 上看 #2 的详情页后说「参数和命令非常乱，没法据此判断该批还是该拒」，看「Silent threads」后说「又是需要我，但在这个页面里什么也做不了」。这一片只改 Console、不改接口：① 保存的审批令牌不再出现在页面 DOM 里（原来是输入框的 value，Owner 选中页面元素时被带进了对话）；② 详情页先给决定卡（批了会发生什么、为什么、出问题怎么退、批完你还要做什么），命令和参数折叠到「技术细节」并保留换行；③ 线程提醒卡说明这是什么、给出线程标题和「打开线程」。「知道了 / 忽略」需要新接口，等 Owner 定。**建单方的约定**：`reason` 的第一段写批了会发生什么，用 Owner 的话
- **第二片在做（2026-10-10 19:50 派给 Cursor，分支 `w31/w61-needs-you`，任务书 `~/agent-work/w61-approval-page/TASK-3.md`）**：Owner 说手机收到通知、打开 Needs you 却什么都没有。只改 Console：Needs you 分三组列出需要他的审批（待批 / 批了待执行 / 结果未知），底部加「最近已处理」（24 小时内关掉的单和恢复的线程，各带一句结果）。要改服务端的两件等 Owner 定：通知第一句写明要不要动手；「结果未知」的收尾动作
- **验收**：手机上 10 秒内说得出最需要处理的事和原因，详情里 30 秒内找得到建议、不回复的后果、影响的目标和执行内容；读不到时显示 Unknown，不显示 0 或「没有需要你的」；360×780、390×844、430×932、600×960、800×1280 及横屏不横向滚动；桌面信息不减少
- **关联**：W-44；W-47；W-48；W-52；W-57；STEP0-PLAN 0.12 节；设计 v4 第 19 节

### W-62

**Ops Console · 协作进展看得见（Owner 2026-10-10）**

- **类别**：道
- **状态**：在做（Owner 2026-10-12 12:30 定的方向：规则和护栏先做，协作机制搁置，用现在这套协作去做真实的工作，回头按实际运作再看。只做护栏的部分：Needs you 误报的平台一半（TD-316、TD-317）、每条有动作（A15）；整页重新设计搁置，它等调度脚本。）之前：在做（3/11 片已上线；整页设计停着，等调度脚本可信，即 TD-319 关掉）。之前：2026-10-11 16:38：整页设计两稿两次复核（84、87）各 5 处必须改的，没有收敛，暂停；延长的那一次留着，等调度脚本（W-66）第一片落地后换做法再开——判断集中到一个纯函数、页面只照着画，只对调度脚本的格式做（教训第 86 行）。「只留一处登录」（TD-312）的令牌模型设计第 2 稿复核 89：必须改的 2 → 1，用掉延长的那一次在改第 3 稿。Console 的 lint、测试、构建进 CI（TD-313）已派出，是这两份设计的前提。这期间 Owner 用本机看板，Console 上的 Progress 页保持线上的样子。之前：在做：前三片在 PROD（第三片 2026-10-11 11:11，审批单 #7）。第四片（Progress 页总览在前）2026-10-11 14:48 按预算停线：分支 `w31/w62-slice4` 四轮实现、四次复核（67、69、74、78），没有出现过必须改的，但同三类问题每次换地方出现——文档里的字没清理就显示、数据缺失或读失败时报平安或给出件数、颜色说得比数据能证明的多；第 4 轮之前写下的停线条件成立，分支不合并，留作材料。下一步不是再补，是这一页整页重新出设计：照本机看板当天定下来的样子（`work/multi-agent/OWNER-SURFACE-2026-10-11.md` 的 A1–A12），三类问题在结构上堵住（文档里的字只能经一个组件显示；读取状态是类型的一部分，没处理就拿不到数据；颜色只由一个函数给）。设计过复核后再分片实现
- **估算**：进度 3/5 片 · 我还要 2 片 · 你还要 1 次 · 卡在 Claude · 把握 中；2026-10-11 18:10 更新：Console 的检查进 CI（TD-313）仓库这一半做完并进了 infra 主线，等你把流水线应用到集群（一条命令）——多出来的一次；「只留一处登录」的令牌模型设计三稿后按条件停线，重开要你一句话——又一次；进展页整页设计暂停，等调度脚本第一片。其余四次仍是发版单。片数没变：设计仍各算 1 片。此前的说明：前三片已上 PROD。第四片停线后改成先出整页设计（1 片），再分片实现；片数比原来多 1，是把设计单算。后面的片和顺序在 `work/multi-agent/OWNER-SURFACE-2026-10-11.md` 第 4 节。你那四次都是发版单（2026-10-11）
- **现在**：Owner 当天两次问「任务卡在哪了」，两次任务都在正常跑。他的要求：Console 上要有地方显示 Agent 之间协作的进展，否则时间一长他只能当成卡住。W-54 的线程列表只有线程状态和时长，没有「这是哪件事、第几轮、在做什么、做完轮到谁」。临时做法是本机看板 `~/agent-work/status/board.py`
- **下一步**：① 心跳事件带上工作项编号、阶段（实现 / 验收 / 复核 / 发布）、轮次和一句人能读懂的当前动作；headless 任务经包装脚本上报。② 平台按工作项聚合：谁在做、已用时间、同类任务往常用多久、最近一次输出多久前、下一步轮到谁。③ Console 的 Progress 页显示这张表：在跑、比往常慢、可能卡住、进程不在了四种状态分开标；「需要你做的」只列真正要 Owner 动手的。④ 手机首页的系统结论里带一句「N 件事在推进，都正常」或点出慢的那件
- **追加（Owner 2026-10-10 下午，两条）**：⑤ 现状之外给预期：每件事的下一步、预计几点进入下一步；最上面一行是「下一次需要你：哪件事、预计几点」。预计时间按同类步骤的历史用时算，超时顺延并标出，有步骤卡住时显示「估不准」（DESIGN §20.3 第 6、7 条；本机看板已按这个做）。⑥ 卡点台账进 Console：每条坑由什么机制兜着、是否在岗、最近一次触发；新的卡法由运行时起草（DESIGN §20.6）
- **追加（Owner 2026-10-10 下午，第二批）**：⑦ 进展视图在 PROD，和待批项是同一份状态的两个视图：待批项出现在它所属那件事的流程里，进展视图里轮到 Owner 的那一步可以直接批（DESIGN §20.2）。⑧ 台账每行标来源（卡点 / Owner 反馈）和发生的阶段，Console 的「踩过的坑」页可以按阶段回看（DESIGN §20.6）。⑨ 每一步的执行者用它自己的标志显示（Cursor、Claude、Codex 各自的图标；人和集群用固定标记），本机看板已这样做。⑩ 全局计划（Owner 2026-10-10 夜）：进展页最上面是整条路线（第 0 步和运行时各阶段）、现在在哪一段、这一段里已上线 / 在做 / 没开始各是哪些、做完这一段的标准；数据来自本台账，不另抄一份。本机看板已这样做（手工维护的 `roadmap`）。⑪ 现场面板（Agent 说了什么、跑了什么、改了什么，最新在上）和「同时在进行的事」总览也要搬上 Console
- **对齐本机看板（Owner 2026-10-11 凌晨）**：Owner 更喜欢本机看板呈现的信息和流程，要求 PROD 的 Progress 页向它对齐，今后只看 PROD。对齐清单（本机看板的每一块在 PROD 都要有，顺序相同）：① 一句结论和数据新鲜度；② 下一次需要你；③ 统筹线程此刻在做什么；④「需要你做的」分步卡片；⑤ 全局计划与当前位置；⑥ 额度与用量；⑦ 同时在进行的事；⑧ 每件事的步骤条（进度条、已用对往常、预计时间）、现场（最新在上）、「现在 / 下一步 / 轮到你」三行、可能变慢的地方；⑨ 做完的折叠在后；⑩ 实时动态；⑪ 今天已完成的。第二片（10-11 夜里在做）覆盖 ⑤⑥⑦、⑧ 的现场和并行、⑨；第三片补 ③④ 的分步、⑧ 的进度条和三行、⑩⑪，并逐块对照截图。对齐验收通过后，本机看板只作为数据的发布方，不再是 Owner 看的地方。语言（Owner 2026-10-11 定）：系统本身是英文的（状态、标签、按钮、通知的动词，用户面更通用）；系统上跑的工作内容（进展、反馈、结论、单子的理由）用 Owner 和统筹线程交流所用的语言，现在是中文。内容的语言跟着交流走，不写死在系统里；不改规则
- **全局计划要带估算（Owner 2026-10-11 上午）**：他睡醒后看全局计划，一夜之后仍是「14 件已上线，8 件在做，10 件还没开始」，看不出进展，也看不出还要多久。原因有两个：台账里这几件事的状态我整晚没更新；「已上线」按整件事算，而一件事分好几片、上线那一步还要他批。定下的做法：每件未完成的事在台账里有一行 **估算**（做完几片 / 共几片、我还要几片、还要他几次、卡在谁、把握），由统筹线程在每晚收工和每次状态变化时更新；看板的全局计划显示每件事的这一行、整步的预计（剩余片数 ÷ 上一晚实测的每晚片数，给范围，写明依据）和「自上次以来变了什么」。本机看板 10-11 上午已改；Console 的 Progress 页上的同一块是这件事的下一片。
- **细节默认收起（Owner 2026-10-11 上午）**：页面上细节太多。默认只展开正在进行的和需要他的；历史记录（今天已完成的、实时动态、已上线的清单、每件事里已完成的步骤）和说明性的内容（估算依据、额度明细、其余未完成事项的逐项估算）默认收起，他要看时再点开。现在没有步骤在跑、也不在等他的事，整张卡片收成一行。本机看板同日已改；Console 的 Progress 页照此做，归下一片。
- **顶部总览，分段各自展开收起（Owner 2026-10-11 上午）**：一段一段排下来没有重点。页面顶部放一张总览，按他打开页面时要问的问题写，每行一句、点了展开对应的那一段：需要你吗 / 在跑什么、最早几点出结果 / 有没有卡住或失败 / 整体走到哪、还要多久 / 额度有没有要留意的 / 统筹线程在做什么 / 今天做完了什么。下面每一段都是一个可以单独展开、收起的块，带一句话摘要；默认只展开「需要你做的」和「现在在跑的」。本机看板同日已改（页面从约 9400 像素降到约 1750）；Console 的 Progress 页照此做，归下一片。
- **总览以图为主，突出计划和正在跑的（Owner 2026-10-11 上午，两条）**：总览里用图表、状态条来表达，文字只做标签；他最想一眼看到的是两块——计划走到哪、现在在跑什么——这两块要做大，其余的缩成一排小仪表。做法：上面两张大图并排。「计划」：阶段条（当前阶段高亮）、一根分三段的大条（已上线 / 在做 / 没开始，段上写件数）、每件在做的事一根小进度条（做完几片 / 共几片，卡在他那里的带一个点）、三个数字（还要几片、约几个夜晚、还要他几次）。「现在在跑」：每个步骤一行——哪件事、谁在做、一根按平时用时走的进度条、预计几点出结果；等他的和出问题的排在最前并变色。下面一排小块：需要你（数字）、有问题吗（三盏灯）、额度（每个池一根条加窗口已过的刻度）、统筹线程（新鲜度的点）、今天做完（数字）。整页一屏放得下。本机看板同日已改；Console 的 Progress 页照此做，归下一片。
- **他办完之后页面要自己变（Owner 2026-10-11 11:28）**：他在 Console 上批了 #8，本机看板上「需要你做的」那一条没有消失，他问是设计如此还是 bug。是缺口：本机看板的这类步骤由统筹线程手工维护，不读审批记录，统筹线程没在看时就一直挂着。同日补上：需要他的步骤可以带 `closes_when`（一个日志文件和一行能证明事情发生了的文字，例如审批创建出来的那次运行），看到就自己合上并记住，约 10 秒内生效。Console 的 Progress 页第三片已经按真实审批记录显示（单子不再待批，卡片就不再要他做），下一片要保证：任何要他做的事，他做完后页面在一次刷新内反映出来，不依赖 Agent 手工改。
- **「需要你」要写清什么时候（Owner 2026-10-11 11:33）**：他知道有事需要他之后，下一个问题是「什么时候」：现在点了就能办，还是要等到某个时间点才能判断；最晚什么时候；不办会怎样。原来的显示只有一个名字，这几样都看不出来。做法：每件要他做的事固定带四个标记——现在能不能办（能办是实心绿点；还没轮到写明等什么、约几点之后）、最晚什么时候（审批单的过期时间和还剩多久，或者「不限时」）、不办会卡住什么（卡住的写出是哪件事，不卡的写「不挡别的事」）、办完多久见效。排在总览最上面一整行；卡住别的事或有期限的排在前。本机看板同日已改；Console 的 Needs you 和 Progress 页照此做，归下一片，建单时这四样由统筹线程填。
- **追加（Owner 2026-10-11 下午，四条，本机看板 13:15 已照改）**：⑫ 要他办的事只在一个地方、只有一个数：当时顶部写「需要你 1」，下面一段是另一份清单，仪表写「3 个等我接手」（「我」是统筹线程），计划里写「卡在 我」；页面上的「我」从此不指 Agent。⑬ 每件要他办的事写明统筹线程的建议、在哪办（线程里回一句 / Console 的 Needs you 里点 / 他的终端里贴命令）、怎么回；命令直接放在那一行里可复制。⑭「现在在跑 0」要说原因：球在他脚下显示红色，在统筹线程脚下显示琥珀色并写停了多久，队列做完显示绿色。⑮ 他的判断：这些对不上都是手工维护导致的，把手工维护变成系统维护是多 Agent 框架的价值——所以 P6（步骤状态和这份清单由事件生成，即 W-66 的第一半）提前。要求编号 A7、A8、B5，见 OWNER-SURFACE 第 2 节
- **追加（Owner 2026-10-11 14:04，一条，本机看板 14:08 已照改）**：⑯ 在跑的事后面要接上「之后是什么」，排在后面还没开始的事写明各自在等哪一件，并在全局计划里用同一套颜色标出每个工作项现在是在跑、排在接下来、在等他还是没有排到。要求编号 A9。Console 上不并进第四片正在做的第 4 轮（不在修复轮里再加范围），单独一片
- **追加（Owner 2026-10-11 14:10–14:16，两条，本机看板已照改）**：⑰ 业务上够了，页面要更紧凑：排队那一段从右边搬成横跨一行的小卡片，还没轮到的事压成单行，说明文字和下面重复的段落默认收起。⑱ 在跑任务的细节（此刻在想什么、读什么、跑什么命令）要放在显眼的位置并且实时更新：顶部加了「现场」一条。要求编号 A10
- **追加（Owner 2026-10-11 14:20–14:40，四条）**：⑲ 现场面板要有前瞻性：同时跑的任务再多也不撑大页面——一个固定高度的面板，默认合在一起看，点一个任务只看它（已做）。⑳ 任务之间谁等谁要画出来，重点在现在和以后；做完的不能凭空消失，总览留刚做完的一两步，细节页有完整记录；总览只放摘要，点「全部计划」进一整页（已做第一版，先后关系 10 条是手填的）。㉑ 从业务的角度另要一张图：按他能得到的成果排，每件任务写成「做完你能…」（草图已给，五项成果和级别等他定）。要求编号 A11、A12
- **验收**：Owner 不问统筹线程，在 Console 上 10 秒内说得出每件在途的事谁在做、是不是正常、下一步是什么、下一次需要他大概几点；一个任务被人为挂起后，页面在阈值内从「在跑」变成「可能卡住」；一个任务只是比往常慢但仍有输出时，显示「比往常慢」而不是「卡住」
- **关联**：W-54；W-57；W-40（Progress 过渡层）；W-61；`work/multi-agent/LESSONS-from-practice.md` 第 5、22 行

### W-63

**闸门按动作的含义判断：提到不等于运行（2026-10-10，当天第三次）**

- **类别**：道
- **状态**：未开始（排到第 0 步之后：不在第 0 步「做完的标准」那六条里。统筹方 2026-10-12 10:20 定——Owner 当天说每一步具体做什么由统筹方按经验和教训判断，他只确认执行和计划有没有出入；要提前就说「W-n 提前」）
- **估算**：进度 0/2 片 · 我还要 2 片 · 你还要 0 次 · 卡在 我 · 把握 中；闸门是安全件，复核轮次按多的算（2026-10-11）
- **现在**：`preflight.js` 按命令文本匹配。当天三次拦下正常动作：提交信息里写了受保护脚本的文件名；写给别的 Agent 的「不要读某目录」；把「请 Owner 在终端跑的那条命令」写进本机看板的数据文件。每次都换一种不含那段文本的做法绕开，Owner 因此在看板上看不到命令，只能回对话里找
- **下一步**：① 区分「运行 / 读取受保护的东西」和「在数据、提交信息、任务书里提到它」：对 shell 命令做分词，只看会被执行的命令和它的参数位置，heredoc 与引号里的正文不算；② 拒绝时给出机器可读的原因和允许的替代做法；③ 把这三次的原始命令做成回归用例（应放行），再加对应的应拦截用例；④ 两侧（Claude、Cursor）和 Codex 的包装一起改，bump parity-id
- **验收**：三条应放行的用例放行、对应的应拦截用例仍然拦截；`node scripts/agent-guard/test.js` 全过；`bash scripts/check-agent-config-parity.sh` 通过
- **关联**：`work/multi-agent/LESSONS-from-practice.md` 第 12、35 行；Codex 审计的后续（`rolling-reboot.sh --execute` 的机械拒绝、安装器的子串匹配）并进这一道

### W-64

**额度台账与按额度分流（Owner 2026-10-10 夜）**

- **类别**：道
- **状态**：搁置（机制：按额度分流；2026-10-12）。已有的用量显示照用。之前：在做（本机看板按池、按节奏显示，已做；Console 上的同一块随 W-62 第三片，等 #7。还没做：Claude 额度的程序化来源、Cursor 用量从运行日志估算、真正按额度分流）
- **估算**：进度 1/4 片 · 我还要 3 片 · 你还要 1 次 · 卡在 我 · 把握 低；分流怎么做还没有设计。你那一次：Cursor 的用量从哪里取要你定（2026-10-11）
- **现在**：Owner：Cursor、Codex 各有自己的额度重置逻辑，怎样平衡使用这些额度是架构的核心能力，要在后续任务里体现。当天实测：统筹线程（Claude，Max）5 小时窗口用了 4%，**每周额度已用 78%**，还有 1 天 8 小时重置；Cursor 无头运行 21 次、397 分钟、输入 6.49M、输出 2.06M、读缓存 161M tokens（订阅档 Ultra）；Codex 只读复核 18 次、2.18M tokens。Claude 的剩余额度和重置时间能从应用读到；Cursor 和 Codex 只能从运行日志里读到「用了多少」，**剩余多少、什么时候重置读不到**，所以现在的分工（Cursor 实现、Codex 复核、Claude 统筹验收）是按角色定的，不是按额度定的
- **下一步**：① 用量台账：每次无头运行结束记一行（哪家、哪个模型、哪件事、第几轮、用时、tokens），本机看板显示当天合计（已做，`~/agent-work/status/usage.py`）。② 查清 Cursor、Codex 各自在哪里能读到剩余额度和重置时间（CLI、账户页或接口）；读不到的由 Owner 在规则里填上限。③ 进展文档带上用量，Console 的 Progress 页显示每家的已用、剩余、重置时间。④ 分流规则（运行时阶段 2，DESIGN §12）：按任务类型、各家剩余额度和离重置的时间选执行者；某家快用完时把活转给别家；给 Owner 自己的交互使用留出余量；复核的独立性（按模型提供方算）不能因为分流被破坏。⑤ 每件事的预算：超出就停下来换做法或交给人定（和轮次预算是同一条规则）
- **额度是按「池」算的，不是按厂商（Owner 2026-10-11）**：Cursor 一家就有几个池：它自己的模型、别家的模型、Grok 的每周用量，各自重置。当天 Cursor 的无头运行全部用的是 Grok（`grok-4.7-high-fast`），这个池还剩多少不知道；它一旦用完，实现的活会落回 Claude，而 Claude 恰好是最紧的。所以台账和分流都以「池」为单位：每个池记厂商、模型、周期、已用、重置时间；每种执行者（厂商 + 模型）对应一个池；每类任务有一条按顺序的备选链（例如实现：Cursor·Grok → Cursor 自己的模型 → Codex → Claude），切换时仍要保证复核方和实现方不是同一家。已知：Claude 每周已用 78%；Codex 每周已用 3%（10-17 重置，可从它的会话日志读到）；Cursor 三个池读不到，要 Owner 提供或同意读账户页。要先验证的备选：Codex 做实现（它现在只做只读复核）、Cursor 换成自己的模型
- **看节奏，不看百分比（Owner 2026-10-11）**：百分比单看会得出相反的结论。当晚的例子：Claude 每周 78%、Codex 每周 3%，我据此写了「把复核和分析挪给 Codex」。按窗口位置重算：Claude 的窗口已过 81.5%，78% 在线内，剩 22 点、31 小时，每天可用 17 点，按本周平均（每天 13.7 点）到重置时约 96%，然后清零；Codex 的窗口才开了 2 小时，3% 是两次复核用掉的，近 33 小时实测每天用 15.2 点，而每天只可用 14 点，照这个强度会在重置前约半天用完。结论反过来：Codex 没有余量再接实现的活，Claude 到周一早上之前不是瓶颈。每个池要算的五个数：已用、窗口已过比例、每天可用（剩余 ÷ 剩余天数）、近期每天实际用量（写明依据：实测多少小时，还是窗口平均）、按近期速度到重置时的预计值；预计超过 105% 标「会提前用完，在何时」，低于 90% 标「会剩多少点作废」。分流按这个预计值，不按已用百分比。不满 6 小时的窗口不下结论；几小时的短窗口只限制突发，不用来排一周的活；总额度里的分项上限不算额外的一份。重置时间会变：Codex 原定 10-16 重置的窗口在 10-11 被一个 10-18 重置的新窗口替换，所以每次都重读，不记死。本机看板 `usage.py` 已按此计算并随进展文档发布（`usage.pools`）；Console 显示在 W-62 第三片。Claude 的读数现在要统筹线程手动读，要有程序化来源
- **Cursor 的账号会轮换（Owner 2026-10-11）**：Owner 的做法是一个账号的额度用完就换另一个有额度的账号；当前账号的套餐 10-15 取消是有意的。所以 Cursor 的池要按「当前登录的账号」记，不按厂商记死：换号是 Owner 的动作，换号之后三个池的读数全部重来，要立即重读一次；换号前后无头运行会因为没登录而失败，这种失败要和「任务做坏了」分开，显示成「实现方没有登录，等 Owner」，不消耗轮次。当晚实测（账户 Spending 页）：Cursor Models（Grok 和 Composer，无头运行走这个池）24%、Other Models 100%（按量付费关着，重置前别家模型不可用）、Grok Bot 每周 0%，都写 10-15 重置。结论：10-15 之前 Cursor Models 富余最大，剩下的额度会随账号一起作废，实现的活尽量给它；「在 Cursor 里换别家模型」这条退路现在不通。读数的成本（Owner 关心）：不该每次都由模型去读。Codex 由脚本读本地日志；Cursor 平时用无头运行日志里的 token 数估算，每天最多经浏览器读一次 Spending 页校准（那一页很短；不读 Usage 页的明细表）；页面背后的接口要带登录态，不把他的登录 cookie 放进脚本
- **更正：一次复核花多少，我是推算的，推错了（2026-10-11 02:00 实测）**：上面写「3% 是两次复核用掉的」「一天大约只够 9 次复核」不对。按 Codex 的会话日志逐个会话数：这个每周窗口开了 3 小时，一共用了约 3,500 万 token，其中我的 7 次复核合计 380 万，另一个线程的一个长会话 3,060 万，占九成。按这个比例，一次复核约 0.05 点，不是 1.5 点；Codex 的额度压力来自别的线程的长会话，不来自复核。所以额度台账必须按「谁用的」归因（会话、所在目录、线程），只看总百分比会把别人的消耗算到自己头上，分流也会分错。本机 `usage.py` 已加 `codex.by_consumer`（我的复核 / 别的线程）
- **验收**：Owner 在 Console 上看得到三家当天各用了多少、还剩多少、何时重置；把某一家的额度设成快用完，新任务被分到别家，并且页面写明原因；复核方与实现方仍然不是同一家
- **关联**：DESIGN 第 12 节阶段 2「按额度分流」、阶段 3「网关的计量」；W-62；ADR §12.5

### W-65

**Owner 的感受进系统：随手说一句 → 记下 → 分诊 → 变成工作 → 给回执（Owner 2026-10-10 夜）**

- **类别**：道
- **状态**：在做（「向 Owner 提问」这条路的第一版做完未上线：准备片、服务端 1A、Console 1B 都过了验收和 Codex 复核，三个分支合在一起也验过，2026-10-11 11:12 进了 platform 主线，主线 CI 通过，11:22 上 STG 并核对，Owner 11:26 在 Console 上批了 #8，11:30 上 PROD 并核对（健康检查 200、问题接口已挂上、页面里有问题页的固定文字）；Agent 侧的提问工具随本机代码更新，新开的线程才有；闸门三条规则和两侧规则文件的一行已在 infra 主线。之后还有第二片（到期前提醒、摘要、Progress 待办卡）和第三片（Claude 的提醒钩子）。设计 `work/multi-agent/DESIGN-owner-questions-2026-10-11.md`）
- **估算**：进度 3/5 片 · 我还要 2 片 · 你还要 2 次 · 卡在 我 · 把握 中；第一版三片 10-11 上午已上 PROD。还要你那两次：第二片和第三片各一张发版单（2026-10-11）
- **现在**：Owner 的原话大意：我一边看协作进展一边把实际感受发给你，你把它们排进后续任务，这种交互方式本身很有价值；今后我可能用手机或别的非电脑方式和你交互，这些感受要能形成具体的工作，排进协作架构里落地。当天的人工版：他说了约 20 条，每条都进了卡点台账（标「来源：Owner 反馈」）并落到一个工作项，其中 9 条当天已经上线。缺的是：只能在这台电脑的这个对话里说；说完之后「它变成了什么」只在统筹线程的回复里，过后查不到
- **下一步**：① 回执：每条反馈有一行记录（原话、当时他在看什么、变成了哪个工作项或规则提案或「不做，因为…」、现在的状态），先放进进展文档，Console 上有一块「你说过的」。② 入口：Console 的 Progress 和 Needs you 页上有一个「说一句」的输入框，手机上能用，自动带上他当时在看的那件事；平台存进一个收件箱，统筹的席位读它。③ 分诊的规矩：在线时一分钟内确认收到；当天给出去向；涉及规则放宽的变成待他签的提案，不直接改。④ 运行时里它是一种事件，归参谋长席位；不依赖某一家的应用。过渡办法：用 Claude 手机应用远程接入这个会话（要 Owner 同意打开）
- **看得到的地方要能办（Owner 2026-10-11）**：他在 Progress 页看到「需要你的两件事」，但那一页不能操作；能操作的 Needs you 里又没有这两件事，最后只能回到线程里答。两类都要能就地办完：① 要他批的（例如发正式环境）应该直接是 Needs you 里的一张单，Progress 上的待办行链到那张单；现在多出来的「先在线程里回一声发，我再建单，他再去批」是两处确认同一件事，Owner 当晚定了规则（infra b2878ce，CLAUDE.md §5 与 Cursor 侧同步）：走平台审批单的 PROD 发版，Console 上批这张单就是批准，建单前不用再在线程里点头；建单前要 CI 绿、STG 跑同一个提交并核对过、没有另一张未结的发布单。Progress 的待办行直达那张单、单子批完后待办自动消失，在 W-62 第三片里做；② 要他答的（例如 Cursor 的额度在哪看、给一张截图）现在没有任何入口，要成为一种「问题」记录：在 Console 和手机上能直接回文字或图片，回答有记录，并送回提问的线程。通知里的动词已有 Decide / Check / Look，问题类加一个 Answer
- **验收**：Owner 用手机在 Console 上说一句话，一分钟内看到「收到」，当天看到它的去向；一周后还能查到这句话和它的结果；统筹的席位换一家模型来做，反馈不丢
- **关联**：W-61；W-62；DESIGN §20.6；`work/multi-agent/LESSONS-from-practice.md`（来源：Owner 反馈 的各行）

### W-66

**派工流水线：手工的链条变成脚本，状态由事件生成，不再手抄（Owner 2026-10-10 夜）**

- **类别**：道
- **状态**：在做（三片 2026-10-12 16:43 都做完，现在是并排用：A `rec.py` 的 `fold` / `run` / `observe` 入口，复核 130；B `lane.py` 一条命令派活和记结论，复核 131；C 本机看板多出带〔事件〕标记的工作，由事件生成、不计数。从 16:34 起统筹方每件活都用 `lane.py` 派和记，第一件完整走过的是护栏 ②。它仍然不可信、不接线（`scripts/recorder/STATUS.md`），不参与任何正式环境的决定。到 2026-10-19 看一周的差异，再定手工的进程步骤停不停、`events_view.py` 收不收进仓库；复核留下的可以等的几处在 TD-319。）之前：在做（Owner 2026-10-12 15:01 恢复，做薄。三片：A 命令行能用——`owner-open` 修通、`fold` / `run` / `observe` 三个入口、开着的 Owner 事项带「从几点起」、复核 113 的 3 处答错、一条从入口走到出口的测试（Codex 写，Claude 一侧复核）；B 统筹方派活和收结果走一条命令，由它记事件；C 页面从事件生成，和手工看板并排，对上了就换。做完的标准：统筹方不再手改「在跑 / 做完」这类状态。不做：种错清零、让它参与任何正式环境的决定。）搁置（Owner 2026-10-12 12:30 定的方向：规则和护栏先做，协作机制搁置，用现在这套协作去做真实的工作，回头按实际运作再看）。停在：第一片在主线上，标着不可信、不接线（`scripts/recorder/STATUS.md`）；必须修的清单是 TD-319（6 项）；并排跑的工具在分支 `w31/w66-shadow`（`e2c669d`，没合并、没复核）；并排跑没有开始。恢复条件：回头看时手工看板仍是最费事、最常出错的一环，而厂商没有现成的替代，就从 TD-319 接着做。之前：在做（第一片 2026-10-12 09:29 进了主线，但不可信、没接线，TD-319 关掉才算做完这一片；并排跑一周的办法在 `work/multi-agent/PLAN-recorder-shadow-run-2026-10-12.md`）。2026-10-12 09:10 **Owner 定了做法：「主线选 ②」**——第一片不再加实现轮次，当作还没被信任的代码合进主线（infra `49f31f4`；目录里有 `STATUS.md`），复核 113 的 3 处错和没被拦住的种错登记为 TD-319，是接线前必须修的清单；之后让它跟手工维护的看板并排跑一周，对不上的地方变成测试。被否的两个选项：① 照旧再开一轮（六轮三家实现者都没有一轮做对，不知道还要几轮）；③ 砍规则（要改设计、页面少信息）。推翻这条的话：「第一片撤回」——把合并回退，回到分支上继续。第 8 轮（只补测试）09:25 因为把这台电脑压满被 Owner 叫停，已做的部分在合并里。之前：2026-10-12 04:43 第一片第 6 轮按条件停线（Cursor 实现；Codex 复核 113）：复核 106 的两处答错，一处已关闭（脱敏之后的大小，上界核对为可靠），一处没有关完（写满之后跟残尾时不记断链）；另有两处 `since` 取错。都是会答错的输入，重开要 Owner 一句话。统筹方的验收另发现 1,114 处程序生成的种错没被拦住、被用一条不成立的检查记成等价——这一项只缺测试，已作为第 7 轮交给 Cursor（只改测试）。这是「最多再两轮」的第一轮，第 7 轮是第二轮；到上限，早上给 Owner 列换做法的选项。分支不合并。教训第 103 行。之前：2026-10-11 23:22 第一片第 5 轮按条件停线（Codex 实现，Claude 一侧的子代理复核 106）：交给 Codex 修的几处都已关闭；复核方找到两处更早就在的、会答错的输入（发布没算平台脱敏后的大小，正常文档被平台以 413 拒收；日志超过上限停读而不标断链，其后的 Owner 事项消失、文档仍称完整），另有 37 处种错里 22 处没有测试拦住、等效清单被驳倒 1 条。这是「会答错」，按 Owner 当晚的规矩停线，重开要他一句话。分支 `w31/w66-recorder`（`7786522`）不合并。教训第 101 行。之前：2026-10-11 21:00 第一片第 4 轮按条件停线（复核 105：`Folded` 的槽可写、可伪造，1 处必须改的；统筹方另种的 6 处错有 2 处没被拦住），Owner 当即重开并定了规矩：实现先给 Cursor，同一条线连着两轮没修好就换 Codex 修，谁修的不由谁复查。第 5 轮已交给 Codex（任务书 `~/agent-work/w66-recorder-s1/TASK-5.md`：结果对象只当把手、数据在模块私有的登记表里；种错由程序生成），回来后统筹方重跑验收并替它提交，再由 Claude 的子代理独立复核。教训第 95 行。之前：2026-10-11 19:51 第一片第 3 轮按条件停线（复核 102）：入口一头没有再被找到会崩或说假话的输入；出口 `publish_total` 接受任意文档（2 处），测试没有报告说的那么强（3 处，其中一处统筹方的重跑独立撞到）。不加第四轮，重开要 Owner 一句话；建议重开并换两处形状（折叠结果做成不透明对象；测试强度由仓库里的种错清单自己证明）。教训第 93 行。之前：2026-10-11 18:29 输入处理的重新设计过了独立复核（第 4 稿，复核 99，必须改的 3 → 3 → 1 → 0；Owner 18:20 重开的那一轮）。余下的意见已并入，第一片第 3 轮 18:45 前后交给 Cursor（任务书 `~/agent-work/w66-recorder-s1/TASK-3.md`）。之前：2026-10-11 17:58 输入处理的重新设计第 3 稿按条件停线：三稿三次复核（92、94、97），必须改的 3 → 3 → 1，前一稿的每次全部关闭；剩的一处是一步被声明又被取代、没有记到开始、工作已关闭而进程还活着时会显示 `nobody`。重开要 Owner 一句话（建议重开，只收复核点名的）。教训第 89 行。之前：2026-10-11 16:38 第一片按事先写下的条件停线：第 2 轮的复核 88 又找到 3 种会让计算崩掉的输入（溢出的整数、孤立的代理码、嵌套上万层的一行），另有 11 处应该改的。不再逐个堵，输入处理重新设计（对外只有全函数入口：逐行隔离加整次兜底，靠构造成立，不靠列举），写进同一份设计文档，过复核后第一片做第 3 轮；分支 `w31/w66-recorder` 接着用，不合并。教训第 86 行。之前：在做（第一半「记录事件、由事件生成状态」的设计 2026-10-11 14:32 通过：`work/multi-agent/DESIGN-lane-recorder-2026-10-11.md` 四稿四次复核（68、73、76、77），必须改的 8 → 3 → 1 → 0；中间 14:16 按预算停过一次，Owner 14:17 回「设计继续」重开。实现分四片，第一片（事件文件、纯折叠、发布形状过平台真实的校验、防线；纯本机，不读真实记录、不接命令、不启用发布）已写任务书派出。第二版的分支 `w31/w66-lane-v2` `0a54279` 不合并。「判通过并放行」那一半另出设计）
- **估算**：进度 3/3 片 · 我还要 0 片（并排用到 2026-10-19，那天看差异） · 你还要 0 次 · 卡在 没有 · 把握 中；2026-10-12 17:20 更新：三片各一轮实现加一次复核，当天做完。此前（2026-10-11 18:10）：第一片两轮实现没过复核，输入处理重做的设计三稿后按条件停线（必须改的 3 → 3 → 1），重开要你一句话——这是多出来的一次；另一次仍是 Console 读新字段那一版的发版单。重开后设计一轮约 35 分钟，第一片第 3 轮实现加验收加复核约 1.5 小时，都按一次过算，把握低。此前的说明：设计过了，四片里第一片在做，每片按一次实现加验收加复核算。它是 OWNER-SURFACE 的 P6 前半。「放行」那一半要先出设计，估不出。你那一次是 Console 读新字段那一版的发版单（2026-10-11）
- **现在**：Owner：全局计划是手工维护的、和工作台账是两份，这个差距正是多 Agent 协作架构要补齐的，应该变成自动的流水线。当天的实际情况：同一条链（写任务书 → Cursor 实现 → 统筹线程验收 → Codex 复核 → 修 → 合并 → 主线 CI → 测试环境 → 请 Owner 批）手工走了 7 遍，每一步由统筹线程读输出、敲下一条命令、改看板的任务清单。自动算出来的只有：步骤是否在跑、预计时间、现场、用量。手工维护的有：任务清单和步骤、手工步骤的开始结束、全局计划、台账里各项的状态（当天 W-48、W-49、W-54 上了 PROD 几小时后台账还写着「在做」）、「今天已完成的」、统筹线程自己的状态。每一份手抄的状态都是会漂的地方（LESSONS 第 18 行）
- **下一步**：① 一条命令派工：给出工作项、任务书、仓库和分支，脚本建好工作目录，按固定模板依次跑实现、验收、复核，每一步的结论落成机器可读的文件（验收的 `VERDICT`、复核的 `VERDICT` 和各级问题数、提交号）；看板的任务清单由这些文件生成，不再手写。② 闸门写进模板：复核说「先修」就生成下一轮的任务书草稿并停下等统筹线程确认；超过轮次预算就停；要 Owner 的步骤才停下等他。③ 合并、主线 CI、发测试环境也进同一条链，每一步的证据（CI run、STG run、提交号）自动记下。④ 台账的状态由证据更新：发布记录里有这个提交就是「已上线」，不靠人改。⑤ 全局计划由台账生成（当晚已先做了清单这一部分：`~/agent-work/status/roadmap.py`）。这一条做完，就是运行时阶段 0 的任务状态机的雏形，换成运行时的时候把脚本的状态搬进数据库
- **第一版的结果（2026-10-11）**：`lane.py`（分支 `w31/w66-lane`，`431b3c4`、`74b2bcc`、`a28c826`）三轮实现，三轮验收都过（12 → 27 → 34 条测试），三次独立复核（16、17、20）都是「先修」，最后一次还剩 3 个必须改：`stop` 之后 `retry` 可以绕过复核的否决和轮次预算；恢复时可能按旧记录杀掉编号被复用的无关进程组；未跟踪文件的检查会被 Git 配置关掉。第 3 轮是统筹方自己延的唯一一次，按预算规则不再延，**不合并**。这是预算规则第一次真的拦住统筹方。没过的根因有两条：① 这是一个守门的程序，却先实现后复核，没有先复核设计（LESSONS 第 53 行的教训没有用到自己身上）；② 第一版把两件事做在了一起——判定（这一轮算不算过）和管进程（启动、停止、杀进程组、崩溃恢复）。漏洞几乎全在第二件上，而且每加一个命令（`retry`、`stop`）就多出一条绕过判定的路。
- **第二版的设计（待 Codex 复核设计，待 Owner 同意再给实现预算）**：只做判定和记账，不管进程。① 一个纯函数：输入是一轮的产物（各步的退出码、验收的最后一行、复核的首行和尾行、各仓库的 HEAD 和工作树是否干净），输出是状态和原因；没有子进程、没有信号、没有恢复。② 结论只增不改：一轮里一旦记下复核的结论，这一轮不能再复核；「先修」只能经下一轮出去，下一轮受预算约束；没有 `retry`。③ 启动步骤只做三件事：起进程、等它结束、记下退出码；驱动中途死了，这一步的状态是「结果未知」，由人看过后写明结论（和平台审批单的「结果未知」同一个做法），程序不杀任何进程、不自动重跑。④ 内容检查显式带 `--untracked-files=all`，不受本机 Git 配置影响。⑤ 先写设计、先复核设计，再实现。目标是几百行，而不是一千三百行
- **指派的规矩（Owner 2026-10-11 21:00，已在用）**：① 实现先给 Cursor。② 同一条线同一位实现者连着两轮没修好，换发现问题的那一家（现在是 Codex）来修。③ 谁修的不由谁复查：Cursor 修的由 Codex 查；Codex 修的由 Claude 一侧查（独立的子代理复核，加统筹方的程序验收）。脚本的「放行」一半按这三条指派，每一轮的实现者和复核者记在事件里；和下面「按额度指派」冲突时，先保「修的人不复查」。第一次按它走的是本项第一片第 5 轮。
- **停线的规矩（Owner 2026-10-11 23:15「规则同意」，已生效）**：复核或验收的发现分两种。① 找到一个会答错的输入（判定错、两份实现不一致、页面会显示假话）：照旧按条件停线，重开要 Owner 一句话。② 行为没有错，只是某条规则缺测试（一处种错没有测试拦住、覆盖表里漏了一个位置）：不算停线——统筹方补上测试，再送独立复核；每条线最多两次，第三次照 ① 办。两种都照旧记进教训台账，补测试的那一轮照旧由不是作者的一方复核，复核没给出结论不算过。这条规矩不改变：发布、PROD、D10、凭证、审批单仍只有 Owner 能定。第一次适用：冻结协议第一片第 4 轮（两处缺测试）和本项第一片第 5 轮（`since` 取最早起点缺测试）。
- **指派规矩再改一处（Owner 2026-10-12 13:24，在用）**：他的话：发现了问题最好你自己修，或者让 Codex 去修；Cursor 的模型修不了。落成规矩：**复核或验收发现的问题，由统筹方自己修或交 Codex 修，不退回 Cursor**；Cursor 只做第一轮实现。下面细化稿里的第 ① 条（局部的错退回原实现者修一次）对 Cursor 不再适用；第 ② ③ 条和「谁修的不由谁复查」不变。Codex 的沙箱跑不了要监听端口的测试，那部分由统筹方替它跑、替它提交；Codex 修的由 Claude 一侧复核。统筹方的记录（不是反对）：当天 Cursor 修好过一次（心跳第 5 轮），也有连着两轮没修好的；数据还少，照他的话办。
- **指派规矩的细化（Owner 2026-10-12 10:08 采纳，在用；起因是他 2026-10-11 21:02 提的问题：是两轮不过才换，还是一轮不过就换）**：门槛不只看次数，看没修好的是哪一类。① 局部的错、复核已给出改法：退回原实现者修一次（依据：TD-313 第 2、3 轮就是这样修好的；Cursor 的额度最宽）。② 同一类问题第二次出现，或实现者的报告与统筹方重跑的结果对不上：一次就换发现问题的那一家修，不等第二轮（依据：本项第一片「测试没有报告说的那么强」在第 3、4 轮各出现一次）。③ 设计有缺口（规范里有词没定义）：不换人，退回设计（依据：本项第一片四次停线里约一半属于这一类，换实现者不会好）。「连着两轮没修好就换」保留为上限。不建议一律「一次就换」的理由：Codex 每修一次要 Claude 一侧复查一次，而 Claude 的额度最紧；Codex 同时是复核方；Codex 当实现者只有本项第一片第 5 轮这一条数据。要记的数：每一轮的实现者、复核者、必须改的条数和各属哪一类、下一轮关没关掉、各家花的额度——攒够几条线再调门槛，这些字段由脚本的事件带出来。
- **主机负载的规矩（草案，待 Owner 定；Owner 2026-10-12 09:33 提出：页面上要显示工作主机的 CPU，长时间过高要有规则）**：起因见教训第 105 行。统筹方的建议分三层。① **派活时限住**：重活（全量种错、整套测试、构建）同一台主机同一时间只跑一件，由派活的包装脚本用主机级的锁来拦；每件的并行进程数不超过核数的一半（这台 10 核，上限 5）；跑完自己清临时副本。降的是「同时开几个」，不是「多久跑一次」——这次的原因是并行，不是频率。② **跑的时候盯**：看护脚本每分钟采负载 ÷ 核数、交换区占用、空闲内存。负载超过核数 1.5 倍持续 10 分钟 → 记一笔、页面变黄；超过 3 倍持续 5 分钟，或交换区占用过 80% 且空闲内存低于 15% → 自动暂停最后起的那件重活（暂停不是杀掉，降下来自动继续），并记进交接记录。③ **什么才算异常**：暂停之后 15 分钟还降不下来，或者没有任何活在跑而负载仍超过核数 → 泄漏或孤儿进程，这时才进「需要你」，带上是哪个进程、建议怎么办和动作。高而有进展不算异常，不打扰 Owner。④ **页面**：OWNER-SURFACE A16。阈值是统筹方按一次实测估的（负载到核数 8 倍时机器已经明显卡），没有第二个样本；采纳后头两周可以只记录、不自动暂停，用记录来校阈值。在 Owner 说「负载规矩同意」之前，统筹方只手工守第 ① 条，不自动暂停任何东西。
- **停线之后 Owner 不在时的默认动作（草案，待 Owner 定；改的是 2026-10-11 23:15 那条停线规矩里「重开要 Owner 一句话」这半句）**：起因见教训第 106 行——从 10-11 下午到 10-12 早上 10 次停线提问合计等了约 7 小时，10 次都按建议办；10-12 夜里主线等了 4 小时 24 分。统筹方的建议：一条线按规矩停下时，照旧先把问题、几个选项和建议写出来；Owner 30 分钟内没回，统筹方按写下的建议走一步，只限三种——换一家实现者再开一轮、改成只补测试、当作不可信的代码合进主线（不接线，带必须修的清单）。每次记下选了什么、否了什么、怎么一句话撤回；Owner 回来看到的是「已按建议做了，可以撤回」，不是「请你定」。同一条线在他回来之前最多自己走两步，再停就等他。**仍然只归 Owner**：让任何东西读它的输出（接线）、发版、正式环境、冻结协议上线、D10、凭证、审批单。说明：10-11 夜统筹方提过「设计类的线自己重开」，Owner 没有采纳；这一稿范围更小（只有不接线的才算、最多两步、每步可撤回），并带了实测的等待时间。Owner 回「停线默认动作同意」之前，照现在的规矩等他。
- **等待的规矩（Owner 2026-10-12 09:55 采纳，在用）**：全文 `work/multi-agent/RULE-waits-2026-10-12.md`，需求 OWNER-SURFACE A18。每个等待登记四样（等什么、从几点起、上限、超了叫谁），按等的对象分七类定上限和默认动作；上面「主机负载」和「停线之后 Owner 不在时的默认动作」两条草案并进了这一份，不再单独存在。它改了 2026-10-11 23:15 停线规矩的半句：停线不变，Owner 30 分钟没回时统筹方按写下的建议走可撤回的一步，同一条线最多两步。第 5 类（只归 Owner 的事）永不自动做。Owner 采纳时说明：没卡住的发版不该找他，应当自动——见该文件第 6 节和 W-56。现在是「只有文字加统筹方手工」这一档。
- **知识库（Owner 2026-10-11 夜；只是需求，以后再出设计）**：Owner：多 Agent 协作中遇到的新问题怎么解决本身就是经验，要落成知识库，是协作架构的一部分。已有的一半在 DESIGN §20.6（经验进运行时和 Console）；当晚补进去的四条需求里有两条落在本项的后半段：派工时按席位和任务种类把相关的教训放进任务书、复核书带同一组逐项核对；各家 Agent 的能力、习性和额度作为「指派」用的数据，从统筹席位的记忆搬进仓库。第一步是当晚的清点（95 条教训各在哪一档）。
- **按额度指派（Owner 2026-10-11 傍晚；只是需求，挂在后半段，以后再出设计）**：Owner 的话：几个 Agent 提供商的用量要能调配，一家到了就换另一家；重置策略各不相同（Cursor 按月一个大池、中间不限速；Claude 和 Codex 按周，另有几小时的短窗口），最好做得智能，甚至让大模型来指派。当天讨论的要点：① 每个池算两个数——现在能接多大的活（短窗口和长窗口剩余里较小的）、富余还是吃紧（剩余额度比例减剩余时间比例；临近重置还剩很多的先用）。② 任务中途没额度，四层办法：派之前按这类任务的实测用量比对余量，不够就不派；包装脚本把「卡在额度」和「任务失败」分开，不计停线轮数；活留在文件里（任务书、分支上的提交、进度文件，做到一个节点就提交并更新），换一家读这三样就能接；等重置还是换人，看截止时间和换手成本。③ 模型提议、规则把关：规则写成代码（作者和独立复核不是同一家；任何时候至少两家有余量；给统筹留底；硬边界），模型只管在合规的选项里选更合适的，每次指派连同当时的读数和理由留痕；指派本身用最小的模型或本地模型。④ 每个任务记四样（谁做的、花了多少、多久、复核结果），用来学「这类活交给谁一次过的可能最大」。**Owner 已定的两条**：额度都紧时主线先拿，其次是等他的事，其余排队；不急的活等重置（最多等到当晚），主线不等、直接换。**没定的**：Cursor 的用量怎么自动读——官方文档里的用量接口（Admin API）只给 Enterprise 团队，个人套餐没有查到；`cursor-agent` 没有用量命令；账户页要登录态，Owner 不同意把登录信息放进脚本。**以后的扩展**（Owner：将来可能一家有多个账号，现在每家只有一个）：池的身份按「提供商 + 账号 + 池」记，多一个账号就是多几个池；同一家的两个账号不算两个独立的复核方；换账号是 Owner 的动作。当天的手工做法：Claude 每周额度到了 91%，设计的起草和修改从 Claude 子代理挪给 Cursor，Codex 照旧复核。
- **验收**：派一件事只敲一条命令；从派工到测试环境，统筹线程只在「复核要求修」和「超预算」时被叫醒；看板、台账、全局计划三处对同一件事的状态一致，且没有一处是手改的；统筹线程每件事花的 tokens 明显下降（对比 W-64 的台账）
- **关联**：W-62；W-64；DESIGN 第 7 节（任务状态机）、第 12 节阶段 0；`work/multi-agent/LESSONS-from-practice.md` 第 18、52 行

### W-67

**协作的运行位置：页面在集群，Agent 分散在多台主机上、靠平台协作，本机只当开发机（Owner 2026-10-11）**

- **类别**：道
- **状态**：搁置（Owner 2026-10-12 12:30 定的方向：规则和护栏先做，协作机制搁置，用现在这套协作去做真实的工作，回头按实际运作再看）。停在：设计第 3 稿没过复核（117、118、119），不是实现依据；边界已定回虚拟机（ADR §3）；50 行只读脚本 `mini-facts.sh` 写好、复核 123 的小问题已改，留在统筹方的工作目录里，没请 Owner 跑。恢复条件：真实工作里「本机睡了、机器被压满」造成的停顿多到值得搬，就从「Owner 跑只读脚本 → 出虚拟机方案」接着做；不碰集群的活先考虑厂商的云端环境。之前：在做（2026-10-12 12:13 统筹方定，回到已签架构、不需要另签：Agent 进 mini 上的**虚拟机**（ADR §3），「专用账户」这条偏离不再提。原因：验证专用账户要在跑着带外操作面的机器上改 sudoers、改系统文件、按账户杀进程，安全复核 122 否了（教训 110）。设计第 3 稿里讲边界的部分作废；交接、主机心跳、巡检、验收那些留给第 4 稿。带测试账户的量测材料不用了。下一步：Owner 在 `.52` 上跑一个 50 行的只读脚本 `mini-facts.sh`（过复核 123 之后带给他，约 5 分钟），拿到内存、系统版本、磁盘之后出虚拟机的方案；用哪种虚拟化工具是新的外部依赖，到时列选项请他定。）此前：在做（设计第一稿 `work/multi-agent/DESIGN-host-minimal-2026-10-12.md` 2026-10-12 写出，在复核；未开始时的说明：2026-10-12 10:25 提前：设计和一台 mini 的试点放在调度脚本并排跑的这一周里做，见 W-31「计划调整」第 1 条。先出设计；方向、已签架构里的依据、每类机器能不能当主机、要 Owner 定的事写在 `work/multi-agent/RUNTIME-PLACEMENT-2026-10-11.md`。涉及 Agent 在哪些机器上跑、放哪些凭证、手机从外面怎么进，属于架构级，设计要 Owner 点头）
- **估算**：进度 0/6 片 · 我还要 6 片 · 你还要 4 次 · 卡在 我 · 把握 低；片数是粗估：设计 1 片，一台 mini 试点 1 片，第二台加入并证明跨主机 1 片，记录器和观测搬过去 1 片，统筹搬过去 1 片，收尾 1 片。你那四次：定第 7 节里的几样、在两台 mini 上各登录一次各家命令行、试点结果看一眼、合盖一夜后看一眼（2026-10-11）
- **现在**：Owner 2026-10-11 14:45：进展页是今后多 Agent 协作的一部分，他要用手机交互；本机（Mac Pro）不能 7×24 开着，应该放到 Mac mini 上。现状分三层：① 页面——今天反复打磨的是本机 `127.0.0.1:8799` 上的原型，定下来的样子进 Console 的 Progress 页（W-62 第四片在做），Console 在集群上 7×24，手机能开；② 数据——Console 上那一页的内容是本机 `board2.py` 每 15 秒推上去的，本机一睡，页面过 5 分钟标成过期；③ 执行和统筹——Cursor、Codex 的命令行、统筹线程（Claude 桌面应用里的一个线程）、所有工作目录都在本机，本机一睡全停。硬件定位 Owner 10-07 已定：Mac Pro 开发，两台 Mac mini（`.50`、`.52`，`AGENT_FACTS.md` 里写的是 agent host）跑线程和 Agent，现在上面只有带外操作面和告警转发。已有的相关条目只覆盖零件：W-57 主机心跳、W-50 带外执行器、W-66 状态由事件生成、W-52 网页推送；没有一条写「把执行和统筹搬过去」
- **追加（Owner 2026-10-11 14:55）**：两台 mini 任何一台都可以，两台之间也可以协作；多 Agent 的协作不局限于单台主机，可以分散在不同的服务器上通过网络协作；他提到跑 TWS 的两台 Windows 也可以考虑。统筹方的记录：前三点和已签的架构一致——主机主动来领任务、靠平台上的共享状态协调、主机之间不直接通讯（ADR §1、§12.2 第 2、10 条），设计按「主机是一种角色，与机器无关」来做，两台 mini 起步，并安排一步专门证明跨主机（一台实现、另一台验收；一台失联另一台接手）。第四点和已签的两条相抵：ADR §3 写 Win11 ×2「只有 TWS」，§5 把它们放在到不了平台的交易区；统筹方建议维持，真要用 Windows 当主机就用另一台不跑 TWS 的。这一条是规则，等 Owner 定
- **Owner 定（2026-10-11 15:00）**：跑 TWS 的两台 Windows 现在不上 Agent，架构真正做完之前不上；将来一定会上，但放在最后——它上去就意味着系统真正用实盘数据和真实账户，极其危险，要极其谨慎。本条目的任何一片都不碰这两台机器，也不为它做准备性的接线；到那一步的五条前提写在 `RUNTIME-PLACEMENT-2026-10-11.md` 第 9 节，其中一条是 D10 由他明文解除
- **追加（Owner 2026-10-12 上午）**：他再次说明以后整套协作多半跑在两台 Mac mini 上，问设计支持的是多台 mini 还是单独一台。统筹方清点：设计按多主机做的，现在跑着的七样东西绑在一台机器上（任务书里的本机路径、调度脚本的本机日志和文件锁、平台只留一份进展文档、看护在统筹线程里、统筹方单点、登录和额度、并行上限），逐样列在 `RUNTIME-PLACEMENT-2026-10-11.md` 第 10 节，作为设计和验收的清单。
- **下一步**：① 设计：目标是三层各在该在的地方——页面和交互在集群的 Console；状态由记录器的事件推到平台、平台是唯一来源；执行（各家命令行、记录器、观测、派工循环）在一台 Mac mini 上常驻，带主机心跳。要定的：用哪一台（或两台分工）、mini 上只放只读集群身份和 reporter / operator 令牌而不放管理员凭证、各家命令行的登录怎么放、统筹循环用什么形态常驻（无界面的命令行会话，或桌面应用加远程控制）、他不在家里的网络时手机怎么进 Console。② 试点：在 mini 上跑通一条「验收 + 独立复核」，本机仍是统筹；对一遍 Console 上显示的和实际发生的。③ 记录器和观测搬到 mini（W-66 第 2–4 片做完之后）。④ 统筹循环搬过去；本机的看板只留作改样子的试验台。每一步之后本机合盖 30 分钟，看哪些还在走
- **验收**：本机合盖一整夜，第二天早上 Console 的 Progress 页是当前的，夜里派出的事有结果；他在手机上能看到进展、批单、回答问题、留反馈并看到回执；mini 断电或失联 3 分钟内他收到通知
- **关联**：W-57；W-50；W-52；W-62；W-66；`OWNER-SURFACE-2026-10-11.md` 第 4 节；记忆里的硬件定位（Owner 2026-10-07）；`AGENT_FACTS.md`「L-1 带外操作面」

## 本批没有登记的

- 阶段 0 的 W3：`REQUEST-w3-archive-before-delete-2026-10-05.md` 状态节写 A、B、C 全部完成。
- `REQUEST-symbol-paired-ddl-2026-10-06.md`：台账 §7 写 PROD CHECK 已放宽。
- 三份 REVIEW：开放动作已经收进阶段 0 计划，不另开条目。
- ops-arch 里 VERIFY 已 PASS 的道，以及 cursor-tasks 里报告已交且没有写「未执行」的道。
