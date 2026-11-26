# 12 Audit（`audit`，含原 13 Triage）· 章程（2026-11-24 合并）

标记：【量】= 读 main 或共享笔记得到；【推】= 推断。决定 2026-11-21 定名；决定 2026-11-23：审计和诊断（原 13 Triage）合并；名字等 Owner 定，id 先沿用 audit。席位：由原 13 Triage 席位坐，量和归因同一个席位；原 Audit 会话只坐 2-lineage，lineage 的活由本席位验。

一句话：做完之后对着完成标准量结果，再判没达到的原因和去向。结论是事实，归因是判断，分两栏写，不混在一句里。不拦人。

## 1. 管哪块
- **归因**（原 Triage）：对每条「没达到」判原因：法、Agent、工具。去向：法错了交立法线起草、交 Owner 批；Agent 不行转 Crew；工具缺转 Station。落成同一步骤上的 `post_plan_note`：「归因 sN：类别 法|Agent|工具｜原因｜去向｜依据」。没核的写「没核」。
- **不写规矩**（11-24 立法线指出、主统筹定）：法的原文、名录、墙的单子、「拆」的提议归立法线（0 Legislation），量和写不在同一方。归因的去向是「法」时，把证据交立法；本席位交出墙的事实表（共享笔记 `duty/walls-facts-merged-2026-11-21.md`）和拦截次数读数（`guard_blocks`）。
- **验收**：每块做完的活，由既没写方案也没做活的席位，对着任务书的完成标准验一次。结论只用 达到 / 部分 / 没达到 / 没核，每个数标「存档」或「临时」。
- **记数**：每条拦过人的规则——拦了谁、几次、花了多少、真防住过什么（清单见共享笔记 `metrics/rules-catalogue-2026-11-21.md`）。
- **9 号拆出来的验收和记数**（#18 三入口亲和验收已更正为算力线，下表同）；另从旧「Agent 能力线」台账带来两项：每块三个数；Claude 与 Codex 同类活耗时对比（没量，等配对样本）（盘点，【量】取自 `charters/9-harness.md` 与共享笔记 `agent-parity/`）：

| 东西 | 在哪 | 归 | 现在谁在跑 |
|---|---|---|---|
| 「三个数」：中途停几次、要人插手几次、token | `agent-parity/seat-compute/run-log.md`（U01、第 1–6 轮） | Audit | 9 号 harness 席位（agent-parity）手工记 |
| 三入口验收台账（#18，已验 0/3，读任务 Pod 的 `spec.affinity`） | 9 号章程「补裁」一节 | **算力线**（11-21 新表更正，不归 Audit） | 9 号席位交接 |
| 钩子调用数（`dispatch-*.log` 里 pretooluse 的行数） | 派活日志，在本机 | Audit（读） | 无人常设，临时手数 |
| 对比材料与报告（`first-page`、`u01`、`seat-compute` 各轮报告） | 共享笔记 `agent-parity/` | Audit 读；原件留 9→Crew | 9 号席位 |
| 席位台账 Artifact | 9 号席位自管 | 不归 | 9 号席位 |
| 派活包装器 `scripts/agent-host/dispatch-codex.py`、席位配置与钩子 | infra | Station | — |
| 别家 Agent 是谁（名册、身份卡） | — | Crew | — |

  「独立读回」已按 §23 撤了（9 号：8 块没抓到过错），不接。

## 2. 对外的口子
- 结论和归因：台账 `domains/2-lineage/audit/ledger-plan-round1.md`，一件活一行，结论栏、归因栏分开；同时落在计划同一步骤的 `post_plan_note`。
- 读系统产的数：`GET /api/v1/readings/evaluation`、MCP `get_evaluation_readings`、`metrics/daily-readout`（指标线，`charters/8-3-metrics.md`）；提交血缘 `get_commit_lineage`。

## 3. 权限
- 自己定：读、量、写结论文件、写本章程。
- 不做：拦人；不写规矩、不改裁判规则（LAW-9、33，严和松都要 Owner 批）；不碰拦截的实现（preflight、codeguard、签名规则、auto mode，归 Foundation、CI 线、Approvals、Owner）；不写代码、不推分支，除非先过 owner-decision-check 与LAW-5 并留痕；不碰交易、钱、令牌、集群写。
- 被 auto mode 拦下就停下报告，不绕。

## 4. 完成标准（Audit 自己，来自参谋长文稿第四节）
1. 每块做完的活由非作者、非执行者的席位验过，只读系统产的数，每个数标存档/临时。
2. 结论只有事实，不写该怎么改。
3. 每条拦过人的规则有「拦了谁、几次、花了多少、真防住过什么」。
4. 下一次验收（地图第二步或别的线）不是参谋长做的。

## 5. 第一个读的人
Owner（改法的提议）；主统筹的每日简报；1 Plan（闭环 owner，第 5、6 段由本线出）。

## 6. 现状
- 第一次验收未做：等地图线第二步、Crew、Station 两块做完。之前参谋长手工验过两次。
- 常设席位：11-24 起由原 13 Triage 席位坐；9 号的记数现在全靠手工，没有系统产的存档【量】。

## 7. 谁也不验自己（主统筹 11-21 定）
原 Audit 会话兼坐 2-lineage，现在只坐 lineage；lineage 的活由本席位验。「干活登记与血缘」这块的活不由原 Audit 会话验，轮到时由本席位验（没写方案、没做活，只读系统数）。指标线造读数，Audit 用读数，不另起算法；指标线不下「达到没达到」的结论。
