# 运行时规则（agentrt rules）

Owner 2026-10-14 20:10 「规则 A」：规则正文是 YAML，Owner 用 `ssh-keygen -Y sign -n bifrost-agentrt-rule` 签名，平台用闭合解析器读（不认识的字段、锚点、别名、合并键、显式标签、第二个文档、类型不对，一律拒）。依据：`work/multi-agent/PROPOSAL-agentrt-rules-2026-10-14.md`、设计 v5 §5.2「规则」。

**线上规则只在平台库里**（`agentrt.rule`，只追加）。仓库不再放规则副本（清理第 2 波，2026-11-12 删掉 `prod/`、`stg/`）：副本和线上版本会悄悄分叉，而平台只认库里生效的那一版。

## 1. 怎么查线上规则

```bash
bash bifrost-trade-infra/scripts/agentrt/rule.sh show <rule_id>              # STG，例如 standing-envelope:dev
bash bifrost-trade-infra/scripts/agentrt/rule.sh show <rule_id> --env prod   # PROD
```

`show` 返回当前生效的版本（没有就是最严默认值）。要看历史版本或全部规则，用只读的 `agent_reader` 查库（PROD 库 `bifrost_platform`，STG 库 `bifrost_platform_stg`）：

```sql
SELECT rule_id, rule_version, direction, effective_at, expires_at, signed_by
FROM agentrt.rule ORDER BY rule_id, rule_version;
-- 某一版的正文（签名覆盖的原文）
SELECT body_text FROM agentrt.rule WHERE rule_id = 'job:implementer' ORDER BY rule_version DESC LIMIT 1;
```

## 2. 草稿放哪

任意路径都行，不进仓库：比如会话的 scratchpad。改一条现有规则，先从线上取正文（上面的 `body_text`），存成文件再改，版本号加 1。

## 3. 怎么签

```bash
bash bifrost-trade-infra/scripts/agentrt/rule.sh check <文件>               # 只读：平台会读成什么、上一版是几、是不是收紧
bash bifrost-trade-infra/scripts/agentrt/rule.sh sign <文件> [--env prod]   # Owner：先 check，再签名，再交平台
bash bifrost-trade-infra/scripts/agentrt/rule.sh tighten <文件>             # 交一个收紧，不用签名
```

默认连 STG（`--env prod` 连 PROD），令牌是 `PLATFORM_STG_OPERATOR_TOKEN`（或 PROD 的），从环境或 `bifrost-trade-infra/.env` 读，只进权限 600 的 curl 配置文件。签名覆盖文件的每个字节：改了就要重签。`sign` 在文件旁边生成 `<文件>.sig`，交给平台后就不用留。

## 规则格式（参考）

### 每份规则的头部（签名覆盖这五项）

```yaml
rule_id: standing-envelope:dev     # 六类之一，见下
rule_version: 1                    # 第 1 版必须是 initial，之后每版加 1
direction: initial                 # initial / loosen（要签名）/ tighten（可以不签，平台比较上一版证明是收紧才收）
effective_at: 2026-10-15T00:00:00Z # 带时区的 RFC 3339
expires_at: 2027-01-15T00:00:00Z   # 过期后回到最严默认值，不会退回更松的旧版
```

### 种类

| rule_id | 写什么 | 没有这条规则时 |
|---|---|---|
| `standing-envelope:<租户>` | `tenant`、`max_action`（none / branch）、`budget`（`max_attempts`、`max_wall_hours`）、`executors`、`hosts`（都必须已登记） | 所有 mission 都等 Owner |
| `concurrency` | `per_host`（第 2 轮只能 0 或 1） | 不派活 |
| `budget:<租户>` | `tenant`、`mission`（默认预算）、`attempt_hard_limit_s` | 没写预算的 mission 不落在常备授权内 |
| `job:<岗位>` | `tenant`、`text`（说明书）、`candidates`（`executor`、`provider`、`model_pattern`、`status`） | 这个岗位的任务没人能领 |
| `capability-facts` | `facts`（`executor`、可选 `provider`、`kind`：cannot / must_not / only / prefer、`subject`、可选 `scope`：值是字符串或 true / false） | 不额外排除（种子里 Owner 类的事实只当提议） |
| `routing:<租户>` | `tenant`、`order`（固定 `[capability, quota]`）、`quota_stop_percent`；可选 `min_score_percent`（0–100）+ `min_samples`，两个一起写 | 领活时不看额度线（没有读数的池照常派）；不按成绩刷人 |
| `plan-standing` | `done_rules`、`active_on_lease`（true / false） | 计划的常备授权只有两种内置情形 |
| `card-auto-answer` | `after_seconds`（0–604800；第 1 版写的 `after_minutes`（5–10080）照读）、`kinds`（`blocked` 卡住卡、`plan_question` 计划者的问题、`plan_change` 计划变更、`plan_import` 计划导入、`recorder_import` 记录导入、`mission` 授权外 mission 的决定卡，至少一个）。**只在 STG 放**（Owner 2026-10-20「STG 用 A」，TD-390；PROD 平台不接这个循环）：运行时问的、种类在列、所属 mission 没标 `needs_owner`、开着超过等待时间的卡，由平台回答，记成这条规则的回答，不是 Owner 的：卡有推荐时答推荐项，除非已到的 AI 评估推荐别的项；卡没推荐时，答已到的 AI 评估推荐的项；其余情况答「不改变任何东西」的那项（不做这件、不应用、不启动；计划者问题答它自己的推荐）。答的不是卡推荐的项时写明原因（TD-393）。可选的 `assessment: veto`（唯一取值；第 4 版起，复核 489 A1 / T12，统筹线程 2026-10-22 代 Owner 定 A1）：AI 评估只能把规则从推荐项拦回「不改变任何东西」，不能替它选项；卡没推荐时一律答「不改变任何东西」；卡上没有这一项（没给推荐的计划者问题）就不答、留给 Owner。「不改变任何东西」按选项的 key 认、不按文字：五种决定卡（`blocked`、`plan_change`、`plan_import`、`recorder_import`、`mission`）是平台建的、这一项固定在第二个，key `b`；计划者问题是它自己推荐的那项 | 没有卡被自动回答 |

### 收紧怎么判断（不带签名也能立即生效）

和上一版比：上限只降不升，`card-auto-answer` 的等待（按秒比）只升、`kinds` 只减、`assessment: veto` 加上后不去掉，执行者和主机名单只减不增，`max_action` 只降，候选只能降级、不能新增或升级（漏写的算退役），说明书不能改，能力事实只能加 cannot / must_not、不能删或改，`quota_stop_percent` 只降，成绩门槛（`min_score_percent` / `min_samples`）的任何改动都不算收紧，有效期只缩不延、生效时间不提前。判不出是收紧就按放宽处理，要签名。
