# 2026-10-13 要你动手的事（草稿，等统筹方在线程里说「可以开始」再做）

写给 Owner。两处：Console 上批一张单；终端里三条命令。每一步做完不用回话，统筹方用只读身份自己看结果。
本文件 2026-10-12 晚写成，命令已由统筹方逐条核对、并交 Codex 只读复核（结论见文末）。

## 第 1 步 · Console：批一张平台的正式环境发布单

- **在哪**：Console 的 Needs you。单子由统筹方 10-13 早上建好后出现在那里。
- **批了会发生什么**：正式环境的平台从 `5643820` 升到 `26a10b5`，带两处改动——护栏 ② 的平台一半（单独上线不改变任何行为）和护栏 ③（平台能在指定提交上起 CI；起不来的运行不再回答成功）。约 4 分钟，期间 Console 会短暂断开重连。
- **已核对的**：这个提交主线 CI 全绿；测试环境发的就是它（10-12 18:56），健康检查 200；没有别的未结发布单。
- **没做的检查**：新的「起流水线」代码只跑过测试，没有在测试环境上真的起过一次发布。
- **回退**：再发一次上一个提交（走同一条流水线），统筹方准备单子。

## 第 2 步 · 终端：护栏 ② 的试跑，然后应用（第 1 步发完、统筹方核对过正式环境之后）

前提由统筹方核对：正式环境的平台是 `26a10b5`；没有平台发布在跑；没有未结的发布单。
身份：你自己的集群管理员身份。目录：`~/Desktop/stocks/bifrost-trade-infra`，在主线上（先 `git pull --ff-only`）。

**2a. 试跑两条**（只起一个检查任务：把两个仓库各浅拉一次到临时目录、读 CI 和测试环境的发布记录；不构建、不发布）：

```bash
cd ~/Desktop/stocks/bifrost-trade-infra && python3 scripts/release/platform_prod_gate_trial.py 26a10b5eda62e9164e088e33b6f02b66d98368e4 > /tmp/trial-pass.yaml && kubectl create -f /tmp/trial-pass.yaml
```

```bash
cd ~/Desktop/stocks/bifrost-trade-infra && python3 scripts/release/platform_prod_gate_trial.py 56438205740b19b41dfdce87d55fd6a989ce0477 > /tmp/trial-refuse.yaml && kubectl create -f /tmp/trial-refuse.yaml
```

应当看到（统筹方来读，你不用查）：第一条成功，结果里的提交是 `26a10b5…`；第二条失败，日志里一行
`REFUSED: STG cannot be shown for 56438205…: STG clone commit differs or is ambiguous`。
第一条如果起不来、或者报 `identity cannot read…`：**不要做 2b**，等统筹方说明。

**2b. 应用**（统筹方确认 2a 两条都对之后）：先服务端试算，通过才应用。

```bash
cd ~/Desktop/stocks/bifrost-trade-infra && kubectl apply --dry-run=server -f k8s/cicd/tekton/pipeline-deliver-platform-prod.yaml && kubectl apply -f k8s/cicd/tekton/pipeline-deliver-platform-prod.yaml
```

它改的只有集群里的一个对象：流水线 `cicd/bifrost-deliver-platform-prod`，多一个任务 `check-source`，两个拉代码的任务改成用它核对过的提交。别的 17 条流水线不变（统筹方 10-12 已只读比对）。

**做完之后的效果**：平台的每次正式环境发布，在构建之前先自查「这个提交 CI 是绿的、测试环境最新一次成功发布的就是它」，不成立就拒绝。没有「带红放行」的开关。

**要撤回（也是唯一的越过办法）**：

```bash
cd ~/Desktop/stocks/bifrost-trade-infra && git show 27e4467:k8s/cicd/tekton/pipeline-deliver-platform-prod.yaml | kubectl apply -f -
```

## 不在明天这一次里的

- 护栏 ④（Gitea 备份）的应用：等它过完演练和确认复核、合进主线之后，另给一份。
- TD-309（把流水线的字段归属换给平台，之后改流水线不用你手贴）：另找一天，单独一份。
