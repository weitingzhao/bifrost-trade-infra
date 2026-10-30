# S6-7：infra Gitea 与身份开门操作单

适用 `DESIGN-S6-v3-2026-10-29.md` §9。本单由 Owner 在自己的 Mac 终端执行；脚本交付不等于已开门。S6-7 不发布平台、不改集群 Secret、不签规则、不改 live 开关。S6-8 统筹确认前置、演练与开门时机后，才执行本单的 Gitea 修改。

## 1. 准备与核对

进入包含本次 S6-7 提交的 infra 检出根目录。若仍使用本任务目录，先执行这一条：

```bash
cd ~/agent-work/codex-work-772/infra
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

在任何团队、分支或标签修改之前，先建立本次操作的私有配置快照目录；它不含凭据，不进仓库，保留到 S6-8 签收后：

```bash
umask 077
snapshot_dir="$HOME/gitea-protection-snapshots/s6-7-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$snapshot_dir"
bash scripts/gitea/protect-repo.sh --snapshot "$snapshot_dir/infra-before.json" --owner weitingzhao bifrost-trade-infra
```

成功：退出 0，输出快照位置，文件权限 600；同名文件已存在会拒绝覆盖。此模式只 GET，保存完整分支规则、字段及 API 返回的有效优先顺序，包括原本缺失的规则。将 `snapshot_dir` 的绝对路径记入交接记录，换终端时重新设置为**同一目录**。

每条已存在规则的全部保护字段都必须明确读到且类型有效；缺字段不代表默认值。显式快照和 `--apply` 的自动快照均拒绝不完整响应，在首次写入前停止。不要手工补入 `false`、`0` 或空值；应排查读取问题后重新获取完整快照。API 明确返回的 `null` 列表按空列表处理。

同时用 Owner 在 Gitea 页面**只读记录**以下内容到 `$snapshot_dir/team-and-tags-before.md`（不记录任何凭据），填写完毕才执行第 2、3 节：

- `landing-prod` 原始完整仓库列表，明确 infra 原来是否已在列表；成员、Code 权限、仓库管理权限。
- infra 全部标签保护规则的存在性、模式、允许的用户和团队；没有规则也明确记为“无”。本次脚本不改标签；若现场纠正过配置，恢复时仍以此记录为准。
- 页面与 `infra-before.json` 中规则名、保护字段和顺序一致；若不一致，停止，重新核对后在新目录取快照。

执行期间只由 Owner 一人改这组设置。脚本每步写前重读、写后核验该步及全部其他规则，发现任何差异即停止全部后续写入。Gitea API 没有原子比较更新，最后一次读取与写入之间仍有竞争窗口。

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

匹配遵循 Gitea 1.21.11：普通名称不区分大小写，优先于 glob；同类按创建时间先后取第一个匹配。glob 区分大小写，`/` 为分隔符，花括号中的字符组与转义边界单独解析。脚本保守拒绝所有可能竞争的规则，不依赖它当前排在目标规则后面；不确定的语法也拒绝。例如 `LAND/PROD/job/a1` 和 `{land/prod/[x,y],release/**}` 必须 FAIL，而 `LAND/STG/job/a1`、`{land/stg/[x,y],release/**}` 可保留。

FAIL：先停在这里，由 Owner 在页面核对实际规则及原因，不删除所有规则重来，也不把 dry-run 的退出 0 当作已开门。默认模式返回 0 只表示计划可执行；下面的 `--check` 才要求规则已经生效。

## 3. Owner 修改 Gitea

先保持 infra 落地未启用。若本来已启用，由 S6-8 统筹先按关仓流程停领新件，处理在途项后再改权限；不要在本单里直接修改集群。

1. Gitea → `bifrost` → Teams → `landing-prod`：确认成员只有既有 `agentrt-lander`，Code 为 Write、无仓库管理权限。仓库列表添加 `bifrost-trade-infra`，最终只有 platform 和 infra。Gitea 在保存白名单时核验用户仓库写权限，所以团队授权必须先完成。
2. 马上执行下面这一条，明确写入刚才预览的保护规则：

```bash
bash scripts/gitea/protect-repo.sh --apply --owner weitingzhao bifrost-trade-infra
```

成功：退出 0，包含 `PASS protection`、`set and read back`。每次 `--apply` 在第一次写入前额外将初始 GET 存为私有 `before.json`，打印 `Execution snapshot` 的路径，不增加 Gitea 请求。重复执行应只读取，规则不再修改。

任一写入/读回异常会立即退出，输出已验证动作、最后尝试动作、当前规则存在性、私有 `current.json`（读回完整且有效时）和回退预览命令；不可读时明确状态未知，不继续 PATCH/DELETE 或下一个仓库。当前字段值只存私有文件，不在终端回显。没有自动回退，按第 6 节恢复；整次开门仍以第 1 节快照为准，不能把重跑生成的快照误当成最初状态。

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

### 先紧急撤权

任何验收失败：保持 infra 未启用；若已开门，交统筹先关 infra 并完成在途对账，不影响 platform。若要马上阻断 lander 对 infra 的新增写权限，可由 Owner 临时移除 `landing-prod` 的 infra 仓库授权并将 infra main 推送收回 Owner。**这只是紧急撤权，不等于恢复原状**；初态原本含 lander/infra 时，稍后仍须按快照恢复。不要删除在途分支。恢复带有用户白名单的规则时，Gitea 会核验用户的仓库权限，应在落地保持关闭的条件下先恢复快照所需的团队授权。

### 按执行前快照恢复

1. Owner 按 `$snapshot_dir/team-and-tags-before.md` 恢复团队**完整原列表**、成员和权限。原列表没有 infra 才移除，原来已含 infra 就保留或补回；不固定改成只有 platform。此时保持落地关闭。
2. 先预览分支回退，再执行同一快照：

```bash
bash scripts/gitea/protect-repo.sh --restore "$snapshot_dir/infra-before.json" --owner weitingzhao bifrost-trade-infra
```

```bash
bash scripts/gitea/protect-repo.sh --restore "$snapshot_dir/infra-before.json" --apply --owner weitingzhao bifrost-trade-infra
```

默认回退只 GET 并打印动作；显式 `--apply` 才执行。它先恢复原 main 字段与已删除的 `agent/**`，再删除快照中原本不存在的新规则；原有 landing 规则按原字段保留。每步同样写后严格读回，异常立即停止。回退前也保存一份执行快照。无关规则发生外部变化、未知字段或快照身份不匹配时拒绝自动回退，由 Owner 对照快照逐项协调，不覆盖他人的改动。

载入快照和读取当前状态时同样要求全部保护字段完整、类型有效；旧的不完整快照会在任何恢复写入前被拒绝。恢复只使用有效快照中的字段值，写后逐字段比对全部保护设置，缺字段或值不一致均报 FAIL，不能报告恢复成功。

3. 验证恢复结果，使用快照比较入口：

```bash
bash scripts/gitea/protect-repo.sh --verify-snapshot "$snapshot_dir/infra-before.json" --owner weitingzhao bifrost-trade-infra
```

成功：退出 0 且 `PASS snapshot`，校验原规则存在性、全部保护设置及有效优先关系。恢复不依赖 S6 目标 `--check`；迁移前的 Owner-only main 本来就不满足该目标。

Gitea 不支持通过保护 API 恢复原创建时间。脚本仅自动恢复本次迁移涉及的 `main`、`agent/**`、`land/prod/**`：这三者互不重叠，且快照须通过重叠检查，证明其他规则不会抢占其匹配。其余规则不重建，顺序和字段保持原样，所以重建 agent 规则后的时间变化不改变任何分支的首个匹配规则。若上述条件无法证明，拒绝自动恢复，不能宣称优先关系已恢复，也不要清空全部规则重建。

4. Owner 按 `team-and-tags-before.md` 恢复全部原标签设置，逐条核对原团队列表、成员、权限；将页面核对结果与 `PASS snapshot` 一起交统筹。标签没有 API，本脚本不把分支验证当作团队/标签验收。

| 回退检查项 | 迁移初态：Owner-only main、有 agent、无 landing | 幂等重跑初态：S6 已完整生效 |
|---|---|---|
| main | 仅原 Owner；原审批数、状态检查及其他字段恢复 | 原 Owner + lander，全部原加固保留 |
| agent | 按快照恢复规则及全部原字段 | 原来无规则则保持无规则 |
| landing | 删掉本次新建的保护规则，分支本身不删 | 保留原规则及全部字段 |
| 团队 | 恢复记录中的完整列表；仅在原来没有 infra 时移除 | 原来已有 infra，恢复时仍含 infra |
| 标签 | 按原记录恢复规则存在性、模式与名单 | 同左；原记录不变则不修改 |
| 验收 | `--verify-snapshot` PASS，页面团队/标签一致 | 同左；回退应无多余写入 |

如决定继续保留新 landing 保护或继续删除旧 agent 保护，这是另一次明确的策略变更，不能称为恢复执行前状态。不回滚 token、Secret 或数据库，本单没有改它们。重新开门前取新快照并重新 dry-run。

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

成功：三次语法检查退出 0，测试无失败。提交后还须对交付差值执行 `git diff --check 0d05d4f HEAD` 与 `git diff --check 9e079f2 HEAD`，不能仅检查空工作树。Gitea API 核对依据为 [1.21.11 分支保护实现](https://github.com/go-gitea/gitea/blob/v1.21.11/routers/api/v1/repo/branch.go)：规则列表完整返回，PATCH 仅更新提供的字段。本脚本不扩大其他既有凭据读取渠道。

匹配语义依据：[ProtectedBranch.Match](https://github.com/go-gitea/gitea/blob/v1.21.11/models/git/protected_branch.go)、[规则优先级](https://github.com/go-gitea/gitea/blob/v1.21.11/models/git/protected_branch_list.go)、[gobwas v0.2.3 lexer](https://github.com/gobwas/glob/blob/v0.2.3/syntax/lexer/lexer.go)。
