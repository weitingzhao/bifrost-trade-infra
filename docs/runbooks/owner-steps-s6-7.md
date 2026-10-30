# S6-7：infra Gitea 与身份开门操作单

适用 `DESIGN-S6-v3-2026-10-29.md` §9。本单由 Owner 在自己的 Mac 终端执行；脚本交付不等于已开门。S6-7 不发布平台、不改集群 Secret、不签规则、不改 live 开关。S6-8 统筹确认前置、演练与开门时机后，才执行本单的 Gitea 修改。

## 1. 准备与核对

进入包含本次 S6-7 提交的 infra 检出根目录。若仍使用本任务目录，先执行这一条：

```bash
cd ~/agent-work/codex-work-769/infra
```

换了检出位置就使用该位置；下文命令均在 infra 根执行。核对交付报告中的提交号：

```bash
git log -1 --format=full
```

成功：提交与 `REPORT.md` 相同，尾注含 `Work: W-31`、`Change-Id`。再检查工作树：

```bash
git status --porcelain
```

成功：没有输出。以下命令不要加 `bash -x`，脚本会拒绝；不要把令牌拼到命令行或重定向到日志。

保护脚本继续使用现有 `scripts/gitea/lib.sh` 的凭据渠道：Owner 管理 kubeconfig 建 Gitea port-forward，从既有 bootstrap Secret 取凭据；原有显式环境覆盖仍受支持，没有新增凭据文件。`GET /user` 必须确认凭据属于 `--owner` 指定的管理员。这里使用 Owner 登录名 `weitingzhao`。

身份核验继续在终端隐藏输入现有 Gitea token。STG、PROD、CI 各用自己的读者 token；lander 用已有 `agentrt-lander` token。不重建账户、不换 token、不读写 Secret。`--check` 不需要 kubeconfig，也不会调用 kubectl；令牌仍需既有 user Read、organization Read，以及身份本身需要的 repository scope。

在 Gitea 页面用 Owner 账户记录当前 infra 分支规则、标签规则和 `landing-prod` 团队仓库列表，作为回退依据。执行期间只由 Owner 一人改这组设置；脚本在每次写入前重新读取，发现变化就停，但 Gitea API 没有原子比较更新，最后一次读取与写入之间仍有竞争窗口。

## 2. 先预览

```bash
bash scripts/gitea/protect-repo.sh --owner weitingzhao bifrost-trade-infra
```

这是默认 dry-run，仅 GET。成功退出 0，打印预计执行的 POST / PATCH / DELETE JSON，或说明规则已符合基线；Gitea 设置不变。目标为：

| 规则 | 推送用户 | 合并用户 | 团队 / deploy key / 文件例外 |
|---|---|---|---|
| `main` | `weitingzhao`、`agentrt-lander` | `weitingzhao` | 无团队、禁 deploy key、无 unprotected file patterns |
| `land/prod/**` | `agentrt-lander` | 无 | 同上 |
| `agent/**` | 不建保护规则，已有则删除 | — | 与 platform 的 TD-383 行为一致，允许清理 attempt 分支 |

脚本仅自动迁移一种现有规则：infra main 的已知旧基线，push 用户只有 Owner，其余受核字段均符合目标；只 PATCH push 用户列表，保留审批数、状态检查等其他加固。新建时先保护 `land/prod/**`，再开放 main。其余现有规则差异、必需字段缺失、重复规则、能覆盖 main / agent / land/prod 的其他规则一律 FAIL，该仓库不写入。无关 `release/**`、`land/stg/**` 规则保留。

FAIL：先停在这里，由 Owner 在页面核对实际规则及原因，不删除所有规则重来，也不把 dry-run 的退出 0 当作已开门。默认模式返回 0 只表示计划可执行；下面的 `--check` 才要求规则已经生效。

## 3. Owner 修改 Gitea

先保持 infra 落地未启用。若本来已启用，由 S6-8 统筹先按关仓流程停领新件，处理在途项后再改权限；不要在本单里直接修改集群。

1. Gitea → `bifrost` → Teams → `landing-prod`：确认成员只有既有 `agentrt-lander`，Code 为 Write、无仓库管理权限。仓库列表添加 `bifrost-trade-infra`，最终只有 platform 和 infra。Gitea 在保存白名单时核验用户仓库写权限，所以团队授权必须先完成。
2. 马上执行下面这一条，明确写入刚才预览的保护规则：

```bash
bash scripts/gitea/protect-repo.sh --apply --owner weitingzhao bifrost-trade-infra
```

成功：退出 0，包含 `PASS protection`、`set and read back`。重复执行应只读取，规则不再修改。失败可能已有前面的写入成功；不要假设自动回滚，按第 6 节恢复。

3. Gitea → `bifrost/bifrost-trade-infra` → Settings → Tags：确认既有 `*` 标签规则仅允许 Owner，无团队、无 lander。本次脚本不操作标签规则；Gitea 1.21 的分支规则 API 无法代替标签页面核对。

## 4. 只读验收（逐条执行）

先读回完整分支规则：

```bash
bash scripts/gitea/protect-repo.sh --check --owner weitingzhao bifrost-trade-infra
```

成功：退出 0 且 `PASS protection`。缺失、不匹配、无法读取都退出非零，不修改规则。

核对 STG 读者；提示时输入 `bifrost-platform-reader-stg` 的现有 token：

```bash
bash scripts/gitea/probe-infra-access.sh --owner weitingzhao stg
```

核对 PROD 读者；输入 `bifrost-platform-reader-prod` 的现有 token：

```bash
bash scripts/gitea/probe-infra-access.sh --owner weitingzhao prod
```

核对 CI 读者；输入 `bifrost-ci-reader` 的现有 token：

```bash
bash scripts/gitea/probe-infra-access.sh --owner weitingzhao ci
```

核对落地身份；输入 `agentrt-lander` 的现有 token：

```bash
bash scripts/gitea/probe-infra-access.sh --owner weitingzhao lander
```

每条成功都必须退出 0，最后是 `VERDICT PASS S6-7 infra <身份>`。探针只发送 GET，不执行试推、建 PR、PATCH 空对象或写集群。它合并保护规则检查和身份检查；其中一项失败，总结仍为 FAIL。

读者验证：`pull=true`、`push=false`、`admin=false`、非站点管理员，main 已保护且不可推/合并，fetch 握手 200、receive-pack 握手 403；全分页查询直到空页，不能有任何可写/可管理仓库。既有 `gitea-primary.txt` 已包含 infra，脚本还强制核验 infra，避免自定义清单漏掉它。

lander 验证：platform 与 infra 都可写、都能推 main、不能合 main、无管理权；完整搜索不能出现第三个可写仓库。401、404、500、重定向、缺字段或达到 40 页仍不结束，均不能作为核验成功。网络失败修好后重跑，不开门。

只想独立核对身份时，可以运行：

```bash
bash scripts/gitea/put-reader-token.sh lander --check
```

注意：省略 `--check` 仍是原来的 Secret 安装模式，`replace` 是轮换模式；本单均不用它们。

## 5. 交接 S6-8

将本次提交号、每个命令的退出码和 PASS / FAIL 摘要、Gitea 页面确认项交给统筹。上述 PASS 证明读取到的保护配置和权限符合目标，不证明真正落地、PR/tag 拒绝或并发推送路径已演练。设计要求的 writer（`PROBE_SKIP_PR=1`）和 protection 实际探针会产生临时写入，留给 S6-8 的 Owner 操作；不可把旧的 `probe-gitea-protection.sh` 当作本单的只读探针。S6-8 还须完成 STG 演练、签规则、PROD live 开关及首件验收。

第一版仅开放设计列出的普通统筹文档。Gitea 按分支限推，不提供这次开放的文件路径政策；全部 `k8s/**` 仍由运行时硬底线拒绝，本单不为它开例外。

## 6. 失败回退

- 任何验收失败：保持 infra 未启用；若已开门，交统筹先关 infra 并完成在途对账，不影响 platform。
- 团队刚扩展、保护脚本失败：Owner 在 `landing-prod` 团队移除 infra，保留 platform。这样先撤掉落地身份对 infra 的写权限。
- Owner 在 infra main 规则把 push 用户恢复为仅 Owner，merge 仍仅 Owner；保持 whitelist 开启、无团队、禁 deploy key、无文件例外。保留其他原有加固，按第 1 节记录核对。
- 保留 `land/prod/**` 保护以避免普通 writer 占用保留分支；不要删除在途 landing 分支。`agent/**` 继续采用与 platform 相同的无保护规则状态，不额外放宽其他规则或标签保护。
- 恢复后本版 `--check` / lander 核验会 FAIL，因为它要求 S6 目标；这是关门状态，不能谎报通过。读者可用 `put-reader-token.sh prod --check` 等独立核对；恢复后的团队与 main 配置由 Owner 页面确认并交统筹记录。
- 不回滚 token、Secret 或数据库：本单没有改它们。Gitea 规则写入不是事务，脚本不提供自动回退，重跑前重新 dry-run。

## 7. 离线复验

开发环境需已有 pytest、PyYAML。以下均在 infra 根执行；测试使用假 curl、文件 API 或现有 HTTP handler 的文件传输夹具，不访问真实 Gitea：

```bash
bash -n scripts/gitea/protect-repo.sh
```

```bash
bash -n scripts/gitea/put-reader-token.sh
```

```bash
bash -n scripts/gitea/probe-infra-access.sh
```

```bash
python3 -m pytest -q scripts/gitea/test_protect_repo_offline.py scripts/gitea/test_landing_drill_token.py scripts/gitea/test_put_reader_token.py scripts/gitea/test_gitea_scripts.py
```

成功：三次语法检查退出 0，测试无失败。Gitea API 核对依据为 [1.21.11 分支保护实现](https://github.com/go-gitea/gitea/blob/v1.21.11/routers/api/v1/repo/branch.go)：规则列表完整返回，PATCH 仅更新提供的字段。本脚本不扩大其他既有凭据读取渠道。
