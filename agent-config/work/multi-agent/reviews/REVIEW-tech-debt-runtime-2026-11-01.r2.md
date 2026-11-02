# REVIEW r2 — DESIGN-tech-debt-runtime-2026-11-01.draft.md（r2，684 行）

只读复核。基线重新拉过，没有变化：infra `de152c7`、platform `bfa513d6`。

## 一、r1 的发现改到哪了

| 发现 | 结论 |
|---|---|
| B1 | **已解决（降为 SHOULD-FIX）**：E1、E2′ 的代价重算正确，E3 可行。但「冻结 = Owner 推一次」不完整，「E3 丢了什么」也没说全，见 R1、R2 |
| B2 | **已解决**：三值判定、`flow='manual'`、导入历史验收都写清了。我核对过：25 行都有「验收：PASS」「防线」「后续」，其中 TD-392、TD-384、TD-378 只写「无后续：」，解析器要认这种写法。导入的 PASS 只能用于「导入时就在待签收、之后没离开过」的债，这个范围要在 store 里写死（见 R6） |
| S1 | **意图对，信号选错了**，见 R3 |
| S2、S4、S5、S6、S10、S12 | 已解决 |
| S3 | 已解决；剩一个漏洞，见 R7 |
| S7 | 大部分解决；还剩 R4 |
| S8 | 已改成 T13。前提也核实了：`agent_reader` 能连 PROD 的 `bifrost_platform`，见 `RUN-r2-stars-2026-10-20.md:111` |
| S9 | 改成读 CI 证据是对的方向，但对风险写得太轻，见 R5 |
| S11 | 已解决：STG 由流水线跑迁移（`agentrt-migrate/README.md:34` 一节），PROD 由你建 Job，3a 里有备份和演练 |

## 二、还剩的与新出现的问题

**R1 · SHOULD-FIX · §7.2/§7.3（冻结并不只是推一次）**
- 平台的 AI 评估（TD-391）会在 main 上读 `AGENTRT_LEDGER=bifrost-trade-infra/agent-config/TECH_DEBT.md`，并解析里面的条目：
  - 环境变量设在 `k8s/overlays/platform-{prod,stg}/platform-agentrt-env.patch.yaml:63-64`；
  - 读取和解析在 `server/agentrt_assess.go:134-150`、`:261`。
- 换成指针之后，评估只是找不到条目，不会写进 `NotRead`，等于你选定的功能在 PROD 上悄悄变弱。
- 所以冻结还要两件事：改 platform 代码，让评估从 `agentrt.debt` 读；改 PROD overlay，它属于 `k8s/**` 硬底线，要你推。5.8-6 的验收写着「没有任何仓库脚本再读」，漏掉了这个运行时读者。
- 另外，从 3b 到 5.8-6，`render-tech-debt-page.py` 读到的是指针，你现在看的台账页会空几周。它应该在 3b 就退役。

**R2 · SHOULD-FIX · §7.2 E3 / 风险 1（「丢了什么」写得不诚实）**
- 逻辑备份每天一次（`cronjob-backup.yaml:20` `30 4 * * *`），最多丢一天；保留 14 份日备份加每周冷备（`backup.sh:18,26`），全部放在同一台 NAS 上。
- 「每日快照产物」存在 `agentrt.artifact_blob` 里（`0001_core.sql:43-46`），和真源是同一个库。库坏了它也一起坏，不能当缓解。
- git 能给、E3 给不了的：完整的历史和 blame；不连运行时也能读（agent-06、派活目录里的 Codex、PROD 宕机时）；GitHub 上的一份异地副本。
- 漏了一个选项：放进一个**不在 `gitea-primary.txt` 里的私有 Gitea 仓库**。这样不会同步到 GitHub，能留住 git 历史，也不碰 infra 的硬底线。代价是平台要一份 Gitea 写凭据，它现在只有只读账号（TD-432），这是一个安全决定。把它写进 T6 的选项和代价里。

**R3 · SHOULD-FIX · §2.4（发号前缀依据的环境信号不对）**
- `IsProd()` 读的是 `OPS_VIEWER_ENV`，它管的是人批的东西。
- 真正管「连的是哪个运行时库」的是 `AGENTRT_ENV`：连接池建立时会核对它与本环境的运行时角色一致，否则拒绝（`server/agentrt_wire.go:61-64`）。
- 修法：前缀按 `AGENTRT_ENV` 选；库里再加一道守卫，只有 `current_user = platform_agentrt_prod` 才能写 `TD-`。

**R4 · SHOULD-FIX · §2.2（表草图）**
- `debt_acceptance_run` 里 manual 的 CHECK：`checked_by_actor_id IS DISTINCT FROM created_by_actor_id`。复核者为 NULL 时这个条件也成立，所以没有复核者的 manual PASS 照样能写进去，「库里防自证」落空。要改成 `checked_by IS NOT NULL AND <>`。
- `debt_ref.debt_part_id` 没有外键，应改成 `(debt_part_id, debt_id)` 复合外键，保证引用的是同一条债的段。
- `debt_floor_raised` 在 `debt_writer_ok` 里落进了「其余」那一类，任何线程都能把地板抬上去，而且抬了降不回来。应限定为 owner 或 controller。

**R5 · SHOULD-FIX · §6.4 `ci_test`（CI 绿不能证明那个测试真的跑过）**
- python CI 跑的是 `pytest -m 'not ib and not db'`（`pipeline-ci-python.yaml:218`），带 `ib` 或 `db` 标记的测试根本不跑。
- lint 不卡的仓库（三个插件），没有 pytest 时 CI 照样绿（`:217-220`）。
- CI 不出 JUnit，读不到单个测试的结果。草稿把这条标成〔推断〕，现在可以确认。
- 修法：`ci_test` 只认 lint 卡住的仓库（`:164-166`）加 frontend 和 platform；在提交里核对这个测试没有 `ib`/`db` 标记、Go 没有 build tag。长期办法是让 CI 产出 JUnit（改 infra）。
- T12-B 允许自动关闭之后，这个漏洞会直接放过没验证的修复。

**R6 · SHOULD-FIX · T12 与 §6.2（自动关闭的条件互相打架）**
- T12-B 说导入的 25 条「或者按 B 自动关闭」，但 B 的条件是验收重跑 PASS 加独立复核，导入的 PASS 不满足。
- 6.2 没有「重开」这个转换，2.3 也没有 `debt_reopened` 事件，「7 天内一键重开」无处落地。
- `ci_test`、`promql` 的 PASS 由谁做独立复核，没有定义。

**R7 · NOTE**
- 6.3 要求「该提交的 `ci_seen` 成功」。一次推多个提交时，CI 只跑在推送的最新提交上，中间的提交永远是 Unknown。应改成和 `ci_test` 一样：「main 上有一个包含它、且 CI 成功的后代提交」。
- 3b 的验收写「第一条拿到 TD-489」，应改成「大于地板、不重复」：本机还有没推的提交用过号，`fdf36f8` 就是例子。
- 冻结用的提交，它的父提交必须正好是导入读的那个提交，并且只接受快进推送（`push-main.sh`）；否则中间手写的新债会丢。

## 三、新的待定项

- **T12**：三个选项都是真的。但推荐 B 拿 P0/P1 当「要你签」的标准，不符合「只管定目标、定规则、不可逆的事」（记忆 `feedback_owner_three_duties…`；10-31 你说过「在环上，不在环里」）。DDL、删除、PROD 变更在动手时已经由你批过单，签收只是验收结果，可以重开，不算不可逆。建议改成：只有「关闭时要接受残余风险」（结论 `boundary`、接受的缺口、验收类型是 `owner`）或「涉及改规则」的要你签；其余自动关闭，7 天内能重开，并修好 R5、R6。
- **T13**：推荐 A 与 0009 的先例一致（`0009:966-969` 当时接受了 `agent_reader` 能读正文）。「正文扫描」要写清扫什么，否则就删掉这句。C（Finance 的债不进共享运行时）是真选项，也符合「各产品业务独立」。
- **T14**：B 是凑数的选项。调整计划步不属于你的三件事，应并进 5.8-2 的设计批准里，不单列成待定项。

## 四、TD-473 撞号的证据（5.8-7 的基线要用上）

- 我核实过：`fdf36f8`（11-01 17:41:45，父提交 `8291857`）在 TECH_DEBT.md:3815 登了 TD-473，标题「platform B5 · 外部发布巡检…」。
- `497c6ba`（17:49:03，父提交同样是 `8291857`）在 :3646 也登了 TD-473，标题「research-control · dagster-daemon…」。
- 两者互不为祖先，就是一次真实的并发撞号，统筹在 de152c7 里把自己那批改号成 TD-474 起。
- 草稿 1.1 第 77 行「另一次未核实」和 5.8-7 那一行「git 里测得 0、Owner 报告过 1 次」都应改成：**基线 1 次（`fdf36f8` 对 `497c6ba`），证据是统筹本机一个没推的提交对象，不在 Gitea 上，别人复现不了。**
- 同时写明：推之前就改了号的撞号，git 里永远看不到。冻结以后号由单一发号器发，撞号在结构上不可能。所以 5.8-7 要量的应该是「冻结后有没有人手写号」（preflight 拒绝的次数、改号提交的数量），而不是撞号次数。

## 站得住的

r1 的两个 BLOCKING 都实质解决了，不是只换了说法。E2′ 和 E1 的代价逐条核实无误。三值判定、`flow`、类型化外键、`legacy_imported` 排除名单、`debt_writer_ok`、逐个授权、迁移只能往前加 STG 先行，都是真改了。

VERDICT: PASS
