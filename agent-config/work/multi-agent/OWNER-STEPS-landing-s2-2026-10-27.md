# 4.1 S2 STG 演练：Owner 操作单（2026-10-27）

为什么要做、每个用例的依据：`REPORT-landing-s2-2026-10-27.md`。
你要动手的只有 **4 件**：两次推 platform main（第 1、5 步）、一次推 infra main（第 1 步）、签一条 STG 规则（第 3 步）；外加第 6 步定一个时间。其余由统筹做，统筹每一步做完在统筹线程里告诉你。

命令都能原样运行；输出写进 `/tmp/s2-*.txt`，跑完告诉统筹「跑完了」，统筹去读文件。

---

## 第 1 步 · 你：推第一批（只含 S2 修复）+ infra

**在哪**：本机终端（Claude Desktop 的终端面板或 Terminal.app）。
**做什么**：platform main 快进到 S2 修复 `51ebc966`（三个提交：`89722fd8`，复核 638 后的 `a504b8b4`，复核 640 后的 `51ebc966`；分支 CI 结果见夜班 `REPORT.md`）；infra main 快进到夜班的文档与脚本提交。

```bash
git -C /Users/vision-mac-trader/agent-work/night-1027-r3 -c credential.helper= push http://weitingzhao@192.168.10.73:30300/bifrost/bifrost-platform.git 51ebc96646495a2ade0042dc94b889bee2105c87:refs/heads/main > /tmp/s2-push1.txt 2>&1
```

infra 那条命令在夜班 `~/agent-work/night-2026-10-27/REPORT.md` 的推送清单里（本文件就在那个提交里，写不进自己的提交号）。

**看什么**：输出文件里是 `ae21a15e..51ebc966  … -> main`、`01584b6..… -> main` 这样的一行，没有 `rejected`。

**想省事、不做用例 ①**：第 1 步直接推第二批（第 5 步那条命令），第 5 步跳过。代价是用例 ① 今天不在 STG 上实跑，只有测试覆盖。

## 第 2 步 · 统筹：把 `51ebc966` 发到 STG

统筹持窗口、起 `bifrost-deliver-platform`（revision 钉 `51ebc96646495a2ade0042dc94b889bee2105c87`），发完核对 STG workers 跑的是这个提交、启动日志里没有 `landing drill disabled`。属于 STG 发布范围，不需要你。

## 第 3 步 · 你：签 STG 的落地规则

**在哪**：本机终端（要用你的签名私钥 `~/.ssh/bifrost_release_owner`，可能会问口令——在终端面板里跑，口令提示 Agent 看不到）。
**做什么**：签 `landing:dev` 第 1 版，只在 STG。内容是 CUT §2.3 的第一片规则，唯一不同是 `stg_release: none`（S2 不发 STG，取最紧）；有效期 2026-10-27 起 30 天。

```bash
cd /Users/vision-mac-trader/Desktop/stocks && bash bifrost-trade-infra/scripts/agentrt/rule.sh sign /Users/vision-mac-trader/agent-work/night-1027-infra/agent-config/agentrt-rules/stg/landing-dev.yaml > /tmp/s2-rule-sign.txt 2>&1
```

**看什么**：`/tmp/s2-rule-sign.txt` 里平台先读回规则（`landing:dev`、`rule_version 1`），再显示签名已收下。退出码 0。
**之后**：统筹查 STG 库里出现 `rule:landing:dev` 的 `rule_signed`，以及一条 `landing_enabled`（启用时刻）。

## 第 4 步 · 统筹：正常路径（不需要你）

1. 在 STG 用 `propose_mission` 建一个 mission：tenant dev，repos `[bifrost-platform]`，max_action branch，**不带 `no_merge`**（带了领取闸会判 stale）；standing envelope 内自动 active，不出你的卡片。
2. `propose_tasks` 一件 implement：只改 `console/src/pages/**/*.tsx` 里一处文案（一个文件、几行），`base_commit` = 当时的 platform main。
3. 等 06-stg 做完、验证和 review 通过（约 5 分钟）；演练循环 15 秒内领取（关闭逻辑给首次领取留 2 分钟宽限）。
4. 读回 `note.landing`：`claimed → prepared → branch_intent → branch_pushed → ci_seen → rehearsed`；Gitea 上 `land/stg/<task>/1` 出现后被删；mission 在 rehearsed 之前一直 active，之后 done。

这件候选**不合进 main**：STG 落地身份没有 main 写权限，候选只到 `land/stg/**`；统筹也不会手工合它。

## 第 5 步 · 你 + 统筹：用例 ①（main 前进）和 ④（断点恢复）

1. 第 4 步那件到 `rehearsed` 之后（**一次只起一件**：前一件还在途时新任务会因 `max_in_flight_per_repo` 被拒，2 分钟宽限一过 mission 就关，错过演练——复核 640），统筹照第 4 步再起一件演练任务，等它到 `branch_pushed`、CI 在跑（CI 约 10 分钟），在统筹线程告诉你「现在推」。
2. **你**在这 10 分钟里推第二批（635 签收 Not started、636 TD-445 第 2/3 项及其测试修正，叠在 S2 修复之上；集成分支 CI 结果见夜班 `REPORT.md`）：

```bash
git -C /Users/vision-mac-trader/agent-work/night-1027-r3 -c credential.helper= push http://weitingzhao@192.168.10.73:30300/bifrost/bifrost-platform.git 64adc934926df749e32a1f1e63df80cb0d8c4d2c:refs/heads/main > /tmp/s2-push2.txt 2>&1
```

3. 统筹读回：k=1 记 `discarded`、`why=main_changed`；`land:<task>:2` 在新 main 上 `claimed → prepared`（`M0` = `64adc934…`）。这是用例 ①。
4. k=2 在等 CI 时，统筹把 `64adc934` 发到 STG（workers 会重启）。重启后同一个 op 接着走：没有新的 `prepared`、CI run 名不变，最后 `rehearsed`。这是用例 ④。

「旧 main 红」的那半（红 main 时也先看 main 是否前进）不能在真 main 上造，只由测试覆盖。

## 第 6 步 · 你定：用例 ③ 什么时候做

用例 ③ 要把发布窗口持住 6 小时以上，期间**所有仓库（含 PROD）都发不了版**。

| 选项 | 内容 |
|---|---|
| **A（推荐）** | 今晚 22:00–04:30 CDT 由夜班做：先起一件演练任务等到 CI 绿，夜班 `release.sh hold --what bifrost-platform` 持窗口；读回 `parked{window}`，6 小时后 `failed{bound}`、活动位释放；然后放窗口 |
| B | 不在 STG 实跑，只认 `TestDrillWindowBoundFreesActiveSlotInDatabase`、`TestDrillCIStatesAndWindowBudget`（今晚真库全过） |

**怎么回**：在统筹线程回「S2 ③ 选 A」或「S2 ③ 选 B」。

## 用例 ② 不需要你

「旧的成功、新的失败 → 不放行」要一个能过 STG 验证、却过不了 CI 的候选，而且第一次绿 CI 一出现演练就收尾，没法故意造。由 `TestDrillLatestCIFailureCannotRelease`、`TestLatestCIFences` 和 `TestDrillFinalGateAndRehearsalDatabase/latest_ci` 覆盖；现场自然出现红候选时统筹补记。
