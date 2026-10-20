# 你 10-20 早上的清单（统筹线程整理，夜里会继续更新）

按顺序做。每条写了在哪办、怎么做。命令都在**终端面板里直接输入**（不要用对话里的 `!`）；问口令时立刻输入（06 只等 2 分钟）。

## 1. 06 换新 agentd（约 10 分钟，问 6 次口令）— **你 23:42 做完**，0 failed，两条探针都过

新版 `agentd-7b2dc5f`：Claude 可以在写墙里当实现者（2.4 最后一项）。已钉进 infra `e65915f`，校验和对过。

```bash
bash /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/scripts/agent-host/agent-06-owner.sh update-agentd
```

装完再跑两条探针，各问 1 次口令；都以「every executor is held to its own directories」结尾才算过：

```bash
bash /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/scripts/agent-host/agent-06-owner.sh confine-probe stg
```

```bash
bash /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/scripts/agent-host/agent-06-owner.sh confine-probe prod
```

## 2. 签 STG 的实现岗规则 v2（1 次口令）— **你 23:4x 签完**，STG 读回 v2、claude probation

内容：`job:implementer` 里 exec:claude 从 qualifying 改为 probation（试用），属于放宽，要你签。说明在 `work/multi-agent/RULE-claude-implementer-2026-10-19.md`。遗留风险写在里面：Claude 的命令能出站访问平台 API 和 Gitea，和 cursor 当实现者时一样，不如 codex 的沙箱严。STG 平台已是 `7b2dc5f0`，能读这条规则（只读检查过）。**必须在第 1 步之后签**，否则派给 Claude 的活会落到旧 agentd 上，那里只有只读工具。

```bash
bash /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/scripts/agentrt/rule.sh sign /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/agent-config/agentrt-rules/stg/job-implementer.yaml --env stg
```

签完我在 STG 上走一件 Claude 写、另一家评审的核心任务（执行单 `~/agent-work/stg-walk-claude-impl/RUN.md`）。过了之后再给你 PROD 的单和 PROD 规则签名。

## 3. 要你定的一件事：计划格式加不加「核心类」字段 — **你 23:4x 定 A**，交 2.4 那条线实现

现状：参谋长把你的一句目标拆成任务时，计划格式里没有 `core` 字段，所以拆出来的任务永远不算核心类，「核心代码由 Claude 写」只能靠手工提的任务验。加这个字段属于改公开接口，归你定。
- **A（推荐）**：计划格式加可选的 `core`，参谋长按规则判断哪件是核心类；路由照现有核心类规则走。
- B：不加，核心类任务只由统筹线程手工提。

在这个线程里回「核心字段 A」或「核心字段 B」。

## 3b. ★ 验收那条线的两张单（10-19 23:30 建）— **都办完了**：#50 你批后平台执行；#49 你 23:50 跑完，exit=0：STG 与 PROD 的迁移幂等、重启 redis-agents 流不丢（STG 173→173、PROD 66→66）、杀中继后新 Pod 接着投递，全过

- **#50（C）**逻辑备份恢复演练：只在自己 Pod 里恢复到临时库、逐表核行数，不连在线库。Console 审批页批即可。
- **#49（D）**T19/T21/T31 演练（先 STG 后 PROD，任何一步不对就停；PROD 后台循环停约 30 秒、Agent 信号停十几秒）：Console 上批，然后在终端面板跑单上写的 owner-run 命令（统筹线程 23:4x 在线程里给过），输出在 `/tmp/w31-r2-stars-drills.txt`。

## 3c. PROD：Claude 写核心代码的最后一段（按顺序）

1. **批一张 PROD 合并发布单**：今晚 main 上的全部改动——M-9 与 M-12 收下的八件、Claude 实现者、导航第二片、TD-385、不稳定测试的修复、Claude 的 oneLine 修复，加上夜班的 TD-384（做完就带上）。我早上先把 STG 发到同一个提交并核对，再建单；单子在 Console 审批页，理由第一段写批了会发生什么。
2. **PROD 发完后签 PROD 的实现岗规则 v2**（1 次口令），命令到时给你。
3. 我在 PROD 上走一件同样的核心任务（或等「核心字段 A」上线后由你的下一句目标里自然出现），过了就勾掉第 2 轮 2.4-5 ★。

## 3d. ★ 验收：三条口径要你定（一句话回复即可）

★ 补验那条线 00:2x 交回：三个 ★ 在 STG 和 PROD 都实测完了，证据在 `work/multi-agent/RUN-r2-stars-2026-10-20.md` 第五节。
- **2.1-11**（PROD 库与 redis-agents）：T19 迁移幂等、各身份权限、逻辑备份恢复演练（agentrt 25 张表行数全对）都过；T21、T31 都过。
- **2.2-31**（正式环境基准）：PROD M-15 在 22 分钟内把 6 道题都跑到了结论，4 道通过、2 道答错（Q12 Python、Q20 shell，两轮都错），全程没人插手。
- **2.3-6**（Gate B）：T11、T04、T09 都过，T13 的口径待定。

要你定（推荐都选 A）：
1. **T19 的物理恢复**：A 用逻辑恢复演练判过，整集群物理恢复（38 GB，大头是 GS）挪到 W-68；B 现在就做物理恢复演练。
2. **T13 口径**：A 只按 agentd 交给执行者的环境判（干净，0 个业务键），codex 在它自己 shell 里加的 `GIT_PAGER` 不算；B 按执行者最终的环境判（命中 `GIT_*`，不过）。
3. **两处按现状的改写是否认可**：T31 的「XADD 之后、标记之前」那个毫秒窗口在 PROD 上卡不住，改成验恢复投递、窗口靠 CI 测试；2.2-31 的执行主机从「开发机」改为 06，题目改为 Go 3、TS 1、Python 1、shell 1（第二道 Python 在 bifrost-research，运行时派不出去）。

回「★ 三条 A」或逐条回。你定了以后，我按证据给 2.1-11、2.2-31、2.3-6 提计划变更（完成规则是「手工 + 证据」，会各出一张卡请你确认）。

**可选清理**：PROD Console 上两张卡 `q_fc7959ed100d3053`（Q12）、`q_ddba16413d854638`（Q20），选「Do not do this task」，M-15 就收尾。

## 4. 待你签收的债（在这个线程回「签收 TD-n」或「打回 TD-n：原因」）

TD-371、TD-373、TD-374、TD-381、TD-382、TD-268、TD-342。（新记的 TD-386：决策卡贴的是检查报告的开头、失败原因在结尾——正好拿来在 STG 验「核心字段 A」，见下）每项的「改了什么、验收、防线」写在 `agent-config/TECH_DEBT.md` 顶部「待你签收」一节。

## 夜里做完的（不用你）

- 00:0x：2.5 导航第二片（Needs you 并进 For you、Progress 并进 Work）和 TD-385（发版后页面没样式）合进 main，STG 已是 `05b2c2da`；STG 上验过：首页 `cache-control: no-cache`、缺失的样式文件回 404。
- 合并时 CI 撞上一个不稳定的测试（`TestBenchmark` 每次调用现取时间，跨秒就判成「结果不同」），00:0x 修好（`05b2c2da`），CI 绿。
- **00:13–00:16 STG 走查通过**（M-30）：Claude 在 06 的写墙里实现一件核心类任务（`oneLine` 截断不切坏多字节字符，只改 `executors.go` 和测试），确定性验收通过，codex 评审通过，收下，mission done。这个修复 00:2x 合进 main（`66de6305`，CI 绿）。

## 夜里在跑、早上可能多出来的

- **★ 验收补验**那条线：PROD 演练要建审批单（重启 redis-agents、恢复演练等），单子会出现在 Console 审批页，每张的理由第一段写着批了会发生什么。
- **夜班**：TD-384 修好后，我把今晚 main 上的全部改动（M-9、M-12 收下的八件、Claude 实现者、TD-384）合成一张 PROD 发布单。
- **2.5 导航第二片 + TD-385**：做完上 STG，随同一张 PROD 单。

（统筹线程 10-19 23:40 写；夜里有变化会更新这个文件，并在线程里说。）
