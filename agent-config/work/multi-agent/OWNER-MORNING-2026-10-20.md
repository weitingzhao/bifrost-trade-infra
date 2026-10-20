# 你 10-20 早上的清单（统筹线程整理，夜里会继续更新）

按顺序做。每条写了在哪办、怎么做。命令都在**终端面板里直接输入**（不要用对话里的 `!`）；问口令时立刻输入（06 只等 2 分钟）。

## 1. 06 换新 agentd（约 10 分钟，问 6 次口令）

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

## 2. 签 STG 的实现岗规则 v2（1 次口令）

内容：`job:implementer` 里 exec:claude 从 qualifying 改为 probation（试用），属于放宽，要你签。说明在 `work/multi-agent/RULE-claude-implementer-2026-10-19.md`。遗留风险写在里面：Claude 的命令能出站访问平台 API 和 Gitea，和 cursor 当实现者时一样，不如 codex 的沙箱严。STG 平台已是 `7b2dc5f0`，能读这条规则（只读检查过）。**必须在第 1 步之后签**，否则派给 Claude 的活会落到旧 agentd 上，那里只有只读工具。

```bash
bash /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/scripts/agentrt/rule.sh sign /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/agent-config/agentrt-rules/stg/job-implementer.yaml --env stg
```

签完我在 STG 上走一件 Claude 写、另一家评审的核心任务（执行单 `~/agent-work/stg-walk-claude-impl/RUN.md`）。过了之后再给你 PROD 的单和 PROD 规则签名。

## 3. 要你定的一件事：计划格式加不加「核心类」字段

现状：参谋长把你的一句目标拆成任务时，计划格式里没有 `core` 字段，所以拆出来的任务永远不算核心类，「核心代码由 Claude 写」只能靠手工提的任务验。加这个字段属于改公开接口，归你定。
- **A（推荐）**：计划格式加可选的 `core`，参谋长按规则判断哪件是核心类；路由照现有核心类规则走。
- B：不加，核心类任务只由统筹线程手工提。

在这个线程里回「核心字段 A」或「核心字段 B」。

## 4. 待你签收的债（在这个线程回「签收 TD-n」或「打回 TD-n：原因」）

TD-371、TD-373、TD-374、TD-381、TD-382、TD-268、TD-342。每项的「改了什么、验收、防线」写在 `agent-config/TECH_DEBT.md` 顶部「待你签收」一节。

## 夜里在跑、早上可能多出来的

- **★ 验收补验**那条线：PROD 演练要建审批单（重启 redis-agents、恢复演练等），单子会出现在 Console 审批页，每张的理由第一段写着批了会发生什么。
- **夜班**：TD-384 修好后，我把今晚 main 上的全部改动（M-9、M-12 收下的八件、Claude 实现者、TD-384）合成一张 PROD 发布单。
- **2.5 导航第二片 + TD-385**：做完上 STG，随同一张 PROD 单。

（统筹线程 10-19 23:40 写；夜里有变化会更新这个文件，并在线程里说。）
