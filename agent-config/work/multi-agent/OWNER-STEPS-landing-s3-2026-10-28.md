# 4.1 S3 开门：Owner 操作单（2026-10-28）

依据：`CUT-landing-2026-10-24.md` §11.9（B5 放到开门后，规则 `stg_release: none`）、§11.11（跨块验收与开门顺序）。
进度页：https://claude.ai/artifact/25ncziKDpLGmUH1VtDgszK

你要动手的共 **6 件**：推三次 main（第 1、2、9 步）、批一张发布单（第 4 步）、签一条规则（第 5 步）、在 Gitea 建落地身份并装进集群（第 6 步）、跑权限探针（第 7 步）；最后给一个小目标（第 10 步）。D-L5（第 8 步）已完成。
统筹每次只给你一步；你跑完回一句「跑完了」，统筹去读输出文件核对，再给下一步。命令都能原样运行，输出写进 `/tmp/s3-*.txt`。

---

## 第 1 步 · 你：推 platform main

**在哪**：本机终端（Claude Desktop 的终端面板或 Terminal.app），用你自己的 Gitea 账号输口令。
**做什么**：platform main 从 `9d611d54` 快进到 `b1e26f09`（S3 的 B1、B6、B3、B4 和验收测试，35 个提交；该提交的 CI `bifrost-ci-platform-1793232844` 8 项全过）。推上 main 不会发布任何东西：STG、PROD 都要另外起发布。

```bash
git -C /Users/vision-mac-trader/agent-work/night-1028/platform -c credential.helper= push http://weitingzhao@192.168.10.73:30300/bifrost/bifrost-platform.git b1e26f0991866e0a76d9dcea0254d80d26c89c73:refs/heads/main > /tmp/s3-push-platform.txt 2>&1
```

**看什么**：输出里有 `9d611d54..b1e26f09  b1e26f09… -> main`，没有 `rejected`。
**若 B4 终轮复核 674 还要修**：修完在第 9 步之前再推一次（同样的命令，换提交号），live 打开之前一定是复核后的代码。

## 第 2 步 · 你：推 infra main

**做什么**：infra main 快进到夜班分支 `w31/night-1028-infra` 的头（设计文档 CUT §11.6–§11.11、本操作单、PROD 第 1 版规则文件、`put-reader-token.sh lander`、`protect-repo.sh` 的新基线、PROD workers 挂载落地身份的清单补丁）。命令由统筹在线程里给（本文件就在那个提交里，写不进自己的提交号）。
**会发生什么**：Argo 自动同步 PROD 平台：`platform-workers` 重启一次，挂上一个暂时不存在的可选 Secret，`AGENTRT_LANDING_LIVE=off`。现在 PROD 上的代码不读这几个变量，没有别的影响。

## 第 3 步 · 统筹：发 STG 并核对（不需要你）

持窗口，起 `bifrost-deliver-platform`；核对 STG 跑的是 `b1e26f09`、演练循环照常、`/health` 的 landing 段、问题页与目标详情能打开。

## 第 4 步 · 你：在 Console 批 PROD 发布单（live 关）

**在哪**：ops.bifrost.lan → 审批。统筹建单（C 级），理由第一段写批了会发生什么。
**会发生什么**：PROD 平台换成 `b1e26f09`。live 关着：workers 读 main 做对账、按库结算到限和问题卡，不领取、不推送、不写 mode。统筹发后核对 `/health` 的 `landing` 段（`live: false` 和原因、卡能力五项）。

## 第 5 步 · 你：签 PROD 的落地规则

**在哪**：本机终端面板（要用你的签名私钥，可能会问口令，口令提示 Agent 看不到）。
**做什么**：签 `landing:dev` 第 1 版，只在 PROD。内容与 STG 那份相同（`stg_release: none`），2026-10-29 起 30 天。统筹已在 PROD 只读解析过（`rule.sh check --env prod`：第 1 版、需要签名）。签了不会立刻做任何事：live 打开之前 PROD 不记录启用、不领取。

```bash
cd /Users/vision-mac-trader/Desktop/stocks && bash bifrost-trade-infra/scripts/agentrt/rule.sh sign /Users/vision-mac-trader/agent-work/night-1028/infra/agent-config/agentrt-rules/prod/landing-dev.yaml --env prod > /tmp/s3-rule-sign.txt 2>&1
```

**看什么**：输出文件里平台先读回规则（`landing:dev`、`rule_version 1`），再显示签名已收下；退出码 0。

## 第 6 步 · 你：在 Gitea 建落地身份并装进集群

照 S0 第 4 节建 `agentrt-landing-stg` 的做法，换成 PROD 的落地身份：

1. Gitea → 组织 `bifrost` → Teams → New team `landing-prod`：只选 `bifrost-platform` 一个仓库（不选 All repositories），不准建仓库，Code **Write**，其余 No Access，不选 Administrator。
2. 新账号 `agentrt-lander`，邮箱 `agentrt-lander@bifrost.invalid`，非管理员，只加 `landing-prod` 团队。密码：`openssl rand -base64 24 | tr -d '\n' | pbcopy`。
3. `bifrost-platform` → Settings → Branches → `main` 规则：**push** 白名单加 `agentrt-lander`（保留 `weitingzhao`），**merge** 白名单不加；不开 force push、不开 deploy key。
   `bifrost-trade-infra` 不动（S6 才加）。Settings → Tags 的 `*` 规则不动（只有你）。
4. 无痕窗口用 `agentrt-lander` 登录 → Settings → Applications 建 token `lander-2026-10-28`：repository Read and Write、organization Read、user Read，其余 No Access。复制 token。
5. 装进集群（隐藏输入，粘贴 token；脚本先核对：非管理员、只能写 platform、能推 platform main、不能推 infra main、全分页没有别的可写仓库，再 server dry-run，最后建 Secret）：

```bash
cd /Users/vision-mac-trader/agent-work/night-1028/infra && bash scripts/gitea/put-reader-token.sh lander
```

   末行应为 `==> Secret bifrost-platform-prod/agentrt-lander created (…; account agentrt-lander).`
6. 读回保护规则，并建 `land/prod/**`（只有落地身份能推、谁都不能合）：

```bash
cd /Users/vision-mac-trader/agent-work/night-1028/infra && bash scripts/gitea/protect-repo.sh --owner weitingzhao bifrost-platform bifrost-trade-infra > /tmp/s3-protect.txt 2>&1
```

   应看到 `bifrost-platform main: there as the baseline`、`bifrost-platform land/prod/**: set and read back`、`bifrost-trade-infra main: there as the baseline`。出现 `DIFFERS` 就停，回线程说。

## 第 7 步 · 你：落地身份的权限探针（⑫ 的服务端部分）

token 还在剪贴板时跑（第 6 步第 4 项复制的）。探针从不推 main、不合 PR；platform 上验标签被拒、`land/prod/_probe/…` 临时分支能建能删、main 不动；infra 上验只读；两仓都验不能改保护。命令由统筹在这一步给（读剪贴板进内存、不落盘、跑完清剪贴板）。
落地身份推 platform main 能成功这一条，由第 10 步的第一次真实落地来验。

## 第 8 步 · D-L5：已完成，不用做

2026-10-28 20:2x 统筹读 PROD：M-1、M-2、M-3、M-4、M-13、M-15 都已有 `scope_json.no_merge`（版本均比 D-L5 建单时 +1），STG 按 Owner 10-26 决定不标。这一步划掉。

## 第 9 步 · 你：推 infra main，打开 live

统筹准备一个只改 `k8s/overlays/platform-prod/platform-workers-landing-live.patch.yaml` 一行（`AGENTRT_LANDING_LIVE: "on"`）的提交，给你一条推 infra main 的命令。推上去 Argo 立即同步，PROD workers 重启后写下 mode、开始按规则领取。推之前统筹核对：前 8 步都已完成，`/health` 卡能力五项齐全，platform 跑的是复核后的代码。

## 第 10 步 · 你 + 统筹：第一个小时

- 你在线程里给一个小目标（比如改 Console 上一句文案），统筹建 mission。
- 统筹盯全程：CI 绿 → 第二道闸 → 落地身份推 main → 对账 landed → 关闭取证轮次 → mission done；目标详情的 Landing 块和 `/health` 都看得到。
- 统筹记下 Gitea 真实的拒绝文本，补进 `landinggit` 的 `TestClassifyPush`。
- 任何一项不对：统筹给你一条把 live 改回 `off` 的 infra 推送命令，记进 CUT §11.11，往前修。
