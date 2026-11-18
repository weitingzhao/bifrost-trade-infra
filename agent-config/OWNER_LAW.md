# Owner 定的法（登记表）

Owner 定过的方向，一条一行。**没登记的不算定**：主统筹每记一条他的方向，当天在这里加一行。
这张表是索引，不是规矩本身：规矩写在「落在哪」指的那一节。标「未落」的，规则文件还是旧文字，照规则文件办，别抢跑。

读数（2026-11-17）：头 22 条里已落 11 条；未落 8 条；不落 3 条（两条是统筹的做法，一条他没说过）。第 23 条（章程）、第 24 条（出错先补环境）已落；第 25 条（手机办不完的四样）未落；第 26 条（落地后评拦过人的规则）、第 27 条（「不能做」的理由不许因果倒置）已落，只有文字；第 28 条（领域之间只通过合约说话）已落，只有文字，机器检查未落。第 29 条（改裁判规则，严和松都要他批）已落，只有文字，机器 gate 未落。六类硬边界都已在仓库里。

## 怎么写一行

| 栏 | 写什么 |
|---|---|
| 哪天 | 他说的那天。括号里「转述」表示来源是统筹转述；「统筹」表示是统筹的话、不是他的 |
| 落在哪 | `` `仓库里的路径`「那一节里能逐字找到的一句」 ``，几处用；隔开。路径从 infra 仓库根算起 |
| 机器强制 | 由哪个程序拦；没有就写「只有文字」 |
| 状态 | 「已落」；「未落：卡在哪」；「不落：为什么」 |
| 旧说法 | 被这一条取代、规则文件里不得再出现的句子，每句用「」括起。没有就写 — |

`scripts/check-governance-consistency.sh` 第 8 节读这张表（只看状态以「已落」开头的行）：「落在哪」的文件要在、那一句要逐字找得到；「旧说法」在规则文件里一处都不能有。
规则文件指：`agent-config/CLAUDE.md`、`agent-config/OWNER_EXEC.md`、`agent-config/AGENT_MODES.md`、`agent-config/claude/skills/*/` 下的 `.md`、`docs/RELEASE.md`。
所以把一行改成「已落」之前，先把旧说法从规则文件里清掉；一行落了之后有人把旧说法写回去，检查会红。

## 登记

编号 1–22 沿用 2026-11-14 那次盘点（统筹共享笔记 `brain/direction-vs-repo-gaps-2026-11-14.md`）；新的接着往下排。

| # | 哪天 | 他的话（要点） | 落在哪 | 机器强制 | 状态 | 旧说法 |
|---|---|---|---|---|---|---|
| 1 | 2026-11-14 | 能不能自己做，看有没有后悔药，不看由谁批 | `agent-config/CLAUDE.md` §5（新节，待写） | 签名的发布规则（待重签） | 未落：会改变什么要他批，等发布规则稿和他重签（TD-579） | — |
| 2 | 2026-11-14 | 你自己去执行，为什么需要我来批；先找不用卡的路 | `agent-config/CLAUDE.md` §5 放行规则；`docs/RELEASE.md` 发布策略 | 签名规则的 `allow`、`check_release_policy` | 未落：同上（TD-579） | — |
| 3 | 2026-11-13 | 要他动手的事，手机上要办得完；回电脑前是系统的失败 | `agent-config/OWNER_EXEC.md`「这一节是全仓库唯一的清单」；`agent-config/CLAUDE.md`「要 Owner 动手的事，手机上要办得完」 | 只有文字（执行口是能力，不是强制） | 已落。还只能在电脑上办的几件登记在那张清单里，是缺陷（TD-524、TD-578） | 「Owner 批准后自己跑」「Owner 自己的终端跑」「Owner 自己 `kubectl apply」「Owner 自己再 apply」 |
| 4 | 2026-11-14 | 给拐杖，不给桎梏；只在越边界、收不回、要他动手、被拦这几种情况停 | `agent-config/claude/skills/phase-execution/SKILL.md`「只在这几种情况停下」；`agent-config/claude/skills/batch-execution/SKILL.md`「Crossing a safety boundary」 | 只有文字 | 已落。「架构级决策」那一条还留着，随 #5 改 | 「2 次重试后仍失败」「Verify failed after 2 retries」「verify failure after 2 retries」「验收标准未覆盖的新需求」 |
| 5 | 2026-11-14 | 代码库怎么建怎么维护归 Agent；收得回的不拿去问他 | `agent-config/CLAUDE.md` §5 要点；phase-execution rule 5、rule 10 | 只有文字 | 未落：会改变什么要他批（TD-579） | — |
| 6 | 2026-11-14 | 活不按工序拆，一个 Agent 整件做到上线，只校验结果 | `agent-config/claude/skills/batch-execution/SKILL.md`「block, not by step」 | 只有文字 | 已落。`CLAUDE.md` §2 和 `AGENT_MODES.md` 里按模式划的范围没动，改不改待定（TD-579） | 「Scope constraint: current phase only」 |
| 7 | 2026-11-14 | 协调靠能力，不靠审批 | `agent-config/CLAUDE.md` §5 发布窗口；`docs/RELEASE.md` | 平台的发布窗口和窗口排队 | 未落：会改变什么要问他（TD-579） | — |
| 8 | 2026-11-12 | 过程中不设复核；先落地，事后评 | `agent-config/CLAUDE.md`「理由只写几行」 | 只有文字 | 已落。`docs/RELEASE.md` 里 `additive_ddl` 那句「经独立复核之前」描述的是机器规则的现状，随 #9 改 | 「例如没有独立复核」 |
| 9 | 2026-11-14 | 后悔药够用就行，不叠保险的保险 | `agent-config/CLAUDE.md` §5；`docs/RELEASE.md` 判定 | 签名规则的 `additive_ddl`（现在是 false） | 未落：等只增改库的允许清单做完再改文字，否则文字比机器宽（TD-579） | — |
| 10 | 2026-11-13、11-14（转述） | 交单要短；对话里只说要他做的事，进展写台账 | `agent-config/CLAUDE.md`「交单要短」；`agent-config/claude/skills/phase-execution/SKILL.md`「## Phase N 交单」 | 只有文字 | 已落 | 「完成后输出结构化 Phase 报告」「### 建议的 E2E 验证」 |
| 11 | 2026-11-14 | 席位按领域归类和命名 | `agent-config/CLAUDE.md`「席位按领域归类和命名」 | 只有文字 | 已落（只有一句指针；领域表定稿后搬进仓库） | — |
| 12 | 2026-11-03、11-10 | 他睡觉时不建单；以他亲口说「去睡了」为准 | `agent-config/CLAUDE.md`「Owner 睡觉时不建单」 | 只有文字 | 已落。「他不在时不做会弹权限框的步骤」是统筹的话，没写成规矩，待他定 | — |
| 13 | 2026-11-13（统筹） | 建卡前草稿先发统筹 | 不进规则文件，留在值班自己的清单里 | — | 不落：不是他的话，是过渡做法 | — |
| 14 | 2026-11-13（统筹） | 请合并的分支不再往里推 | `docs/RELEASE.md` 怎么进 main | 只有文字 | 未落：不是他的话，待他定要不要写成规矩（TD-579） | — |
| 15 | 2026-11-12 | 合并做到他手动零次 | `docs/RELEASE.md`；`k8s/cicd/tekton/pipeline-land.yaml` 的 `LANDING_REPOS` | 落地流水线（现在只有 infra、platform） | 未落：先做机器，文字跟着改（TD-579） | — |
| 16 | 2026-11-13 | 专线做专事 | — | — | 不落：是统筹派活的做法，仓库里的 Agent 用不到 | — |
| 17 | 2026-11-13 | 多家 Agent 都能把活做完；法立在系统边界上 | `agent-config/CLAUDE.md` 提交血缘；`agent-config/AGENTS.md` | preflight（Codex 经不经过，两处说法对不上） | 未落：先核现状（TD-579） | — |
| 18 | 2026-11-12 | 每次交单带做完之后的话和花费 | `agent-config/claude/skills/phase-execution/SKILL.md`「花费：token、时间」「做完之后的话」 | 只有文字 | 已落 | — |
| 19 | 2026-11-13 | 能力要在 Ops 上看得到他才认 | `agent-config/claude/skills/phase-execution/SKILL.md`「在 Ops 上怎么看」 | 只有文字 | 已落。platform 仓库 `CLAUDE.md` 里过时的描述没改（TD-579） | — |
| 20 | 2026-11-13（转述） | 新测试用例带出处；说不出的不加 | `agent-config/CLAUDE.md`「新测试用例旁边写一句出处」 | 只有文字 | 已落。案例本放进仓库哪里待他定 | — |
| 21 | 2026-11-14 | 发布失败 Agent 自己能修 | `agent-config/CLAUDE.md`「级别 2026-11-14 按」 | 平台动作目录的级别（platform `api/internal/actions/catalog.go`） | 已落 | — |
| 22 | — | STG 的改库、RBAC 也由 Agent 自己做 | — | — | 不落：他没说过，是盘点时的推断，待他定 | — |
| 23 | 2026-11-15（转述） | 每条线的 ownership、权责范围、目标要立住 | `agent-config/CLAUDE.md`「每条线有一页章程」 | 只有文字（机器不认席位） | 已落。只是写下来了：重叠没裁，平台不按席位放权限 | — |
| 24 | 2026-11-15 | 出了错先问做事的席位缺什么（工具、信息、边界），补上或删掉惹事的东西；加环节要有第一性原理的依据，删最难 | `agent-config/CLAUDE.md`「出了错先补环境，不加环节」「想加环节先答三问，答不出不加」 | 只有文字 | 已落。评工作分「席位没照做」和「环境没给够」、每日读数加「新增几个环节、删几个」是主统筹的理解，没写成规矩 | — |
| 25 | 2026-11-13 | 口令、重签规则、auto mode 脚本、迁移口令这四样，现阶段只能在他电脑上办 | `agent-config/OWNER_EXEC.md` 的回电脑清单 | 没有东西拦着这四样回到终端 | 未落（TD-578）。是第 3 行没做到的那一半；其中三样本身是硬边界 H2、H5、H6，他来做不变，没做到的只是在手机上做 | — |
| 26 | 2026-11-16 | 每件事落地后，把过程中拦过人的规则评一遍：保护什么、拦住了什么、花了多少、真防住过什么；按证据给留、改、删的建议，改和删交他定。好规则保护我们，并且让项目更快更好 | `agent-config/CLAUDE.md`「每件事落地后评一遍拦过人的规则」 | 只有文字 | 已落（文字）。评价表的第一次实做是沟通层落地后 | — |
| 27 | 2026-11-16 | 「不能做」的理由不许因果倒置：不说规则不让，说这条规则保护什么、这次的事会不会造成那种坏事；不会就是误伤，走正门、记下来提修改 | `agent-config/CLAUDE.md`「的理由不许因果倒置」 | 只有文字 | 已落（文字）。评价表的第一次实做是沟通层落地后 | — |
| 28 | 2026-11-16 | 领域之间只通过合约说话；评判和测试只对着合约做（黑盒）；每条线交付都要写明对外合约 | `agent-config/CLAUDE.md`「领域之间只通过合约说话」 | 只有文字（跨领域引用检查、合约版本检查在做） | 已落（文字）；机器检查未落 | — |
| 29 | 2026-11-17 | 裁判规则往严往松都要 Owner 批，运动员不改裁判 | `agent-config/CLAUDE.md`「改裁判规则，严和松都要 Owner 批」 | 只有文字（gate 的机器实现由 CI 线出提议） | 已落（文字）；机器未落 | — |
| 30 | 2026-11-17 | Ops 里不许有靠 Agent 手动维护的内容：页面上每个数、每个列表都从源头现算（仓库里机器可读的清单、库、Prometheus、事件账）；历史基线由系统在当时记下，不手抄进代码；席位自述只当署名带时间的自述 | 本表（`agent-config/CLAUDE.md` 未落） | code-health `scan.sh` 指标 5（`OPS_HARDCODED_FACTS_PLATFORM_BASELINE`，写死的条数只许减）；手写清单它抓不到，靠盘点 | 未落：规则文件还没写 | — |
| 31 | 2026-11-18 | 只有法才通过系统建卡请他批；过渡期他在主统筹线程里直接说的决定算数 | `agent-config/CLAUDE.md`「只有法才建卡请 Owner 批」 | 只有文字 | 已落 | — |
| 32 | 2026-11-18 | 只增不删的生产迁移有明确判断标准，按标准执行，不需要他批 | `agent-config/CLAUDE.md`「只增不删的 agentrt 迁移，标准满足就由 Agent 直接跑」；`agent-config/OWNER_EXEC.md`「只增不删的由 Agent 用」 | 签名规则的 `ddl_reversible`；平台 `run_agentrt_migration`；`releasepolicy/migrationclass.go` 允许清单 | 已落。发布流水线拒绝信息的文字由 CI 线改 | — |
| 33 | 2026-11-18 | 裁判规则可以放松：从第一性原理分析得出的建议可以；只因被拦不算理由 | `agent-config/CLAUDE.md`「放松不是禁区」 | 只有文字 | 已落 | — |
| 34 | 2026-11-18 | Ops 游戏化是人和 Agent 一起做事的具象化：表现和系统分开，人只做人该做的，Agent 的真实工作看得见，万物分档 | `agent-config/CLAUDE.md`「Ops 游戏化是人和 Agent 一起做事的具象化」 | 只有文字 | 已落。方向全文在 charters/10-cockpit.md | — |
| 35 | 2026-11-18 | 执行卡这条路是给他不在电脑前准备的，哪里不通就扩到哪里，要能到他所有的集群服务器 | `agent-config/OWNER_EXEC.md`「要进某台集群节点」 | `scripts/owner-exec/node-run.sh` 生成时拒绝（配方白名单、命令文本绊线）和 selftest（还没进 CI，见 TD-585）；执行口准入对 Trade 命名空间写入的拒绝；平台对 D10 路径的拒绝 | 已落：设备档在 ubt-k3s-05 跑过一次（卡 #602，2026-11-18）；主机档未在集群上跑过；集群外的机器（Mac mini、NAS、ubt-k3s-06）不在内。交易和钱不因此放开（D10、H1） | — |
| 36 | 2026-11-18 | 问题要走完四步：发得出来、被看到、判断真假、真问题处理而假问题修源头。这个循环现在还没建立 | 待写：沟通换代完成后落到各线的处理规矩和 Ops 读数 | 只有文字 | 未落：先完成沟通换代 | — |
| 37 | 2026-11-18 | 要保留的模块都应和总线连通；断开了也没人受影响的，先问它为什么存在，没有理由就删 | 待写：沟通换代的去向表和各线清理规矩 | 只有文字 | 未落：沟通线和解耦线在按此重判。独立报警路、应急路径要有演练证据；有数据的删除和 Trade 仍按硬边界 | — |
| 38 | 2026-11-18 | 简化和清理本身就是回报，需要做就做，不用先证明省了多少 | `agent-config/claude/skills/owner-decision-check/SKILL.md`「简化和清理本身就是回报」 | 只有文字 | 已落 | — |
| 39 | 2026-11-18 | 所有没有意义的手续都需要简化 | `agent-config/claude/skills/owner-decision-check/SKILL.md`「没有意义的手续都要简化」 | 只有文字 | 已落 | — |
| H1 | 2026-07-04、11-13 | 交易和钱：D10 冻结；围栏没立好之前不排进任何波次 | `agent-config/CLAUDE.md`「D10 — 交易执行冻结」「不排进任何波次」「这六类始终是 Owner 的」 | `preflight.js`；签名规则的 `no_d10_paths`；集群准入策略 | 已落 | — |
| H2 | — | 口令和 Secret 不入库、不读 | `agent-config/CLAUDE.md`「不得进仓库的是」「这六类始终是 Owner 的」 | `preflight.js`；CI 的 statics 段 | 已落 | — |
| H3 | — | 有数据的删改要他 | `agent-config/CLAUDE.md`「跑 ddl-apply Job 前先」「这六类始终是 Owner 的」 | 签名规则的 `additive_ddl` | 已落。和 #9 的分界线未落 | — |
| H4 | 2026-10-10 | Trade 的 PROD 发布由他批 | `agent-config/CLAUDE.md`「Trade 的 PROD（`bifrost-deliver-prod`）不在内」；`docs/RELEASE.md`「Trade 的 PROD 发布仍由 Owner 批」 | 签名规则的 `allow` 不含 `bifrost-deliver-prod` | 已落 | — |
| H5 | — | 改签名规则和信任根本身要他 | `docs/RELEASE.md`「改它是信任根变更」 | 平台编译进去的指纹验签 | 已落。2026-11-15 起重签走一张他输码的执行卡（`OWNER_EXEC.md`「重签发布策略」）；改信任根本身仍是一张写明的发布卡 | — |
| H6 | — | auto mode 规则由他应用，Agent 不自改 | `agent-config/CLAUDE.md`「分类器禁止 Agent 改写自己的 auto mode 规则」 | 权限分类器 | 已落 | — |
