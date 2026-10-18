# 运行时规则（agentrt rules）

Owner 2026-10-14 20:10 「规则 A」：规则正文是 YAML，Owner 用 `ssh-keygen -Y sign -n bifrost-agentrt-rule` 签名，平台用闭合解析器读（不认识的字段、锚点、别名、合并键、显式标签、第二个文档、类型不对，一律拒）。依据：`work/multi-agent/PROPOSAL-agentrt-rules-2026-10-14.md`、设计 v5 §5.2「规则」。

## 目录

- `stg/`：STG 的初始规则草稿（Gate A 用）。签名覆盖文件的每个字节：改了就要重签。
- PROD 的规则等 Gate A 过了再按 STG 的结果起草。

## 每份规则的头部（签名覆盖这五项）

```yaml
rule_id: standing-envelope:dev     # 六类之一，见下
rule_version: 1                    # 第 1 版必须是 initial，之后每版加 1
direction: initial                 # initial / loosen（要签名）/ tighten（可以不签，平台比较上一版证明是收紧才收）
effective_at: 2026-10-15T00:00:00Z # 带时区的 RFC 3339
expires_at: 2027-01-15T00:00:00Z   # 过期后回到最严默认值，不会退回更松的旧版
```

## 六类

| rule_id | 写什么 | 没有这条规则时 |
|---|---|---|
| `standing-envelope:<租户>` | `tenant`、`max_action`（none / branch）、`budget`（`max_attempts`、`max_wall_hours`）、`executors`、`hosts`（都必须已登记） | 所有 mission 都等 Owner |
| `concurrency` | `per_host`（第 2 轮只能 0 或 1） | 不派活 |
| `budget:<租户>` | `tenant`、`mission`（默认预算）、`attempt_hard_limit_s` | 没写预算的 mission 不落在常备授权内 |
| `job:<岗位>` | `tenant`、`text`（说明书）、`candidates`（`executor`、`provider`、`model_pattern`、`status`） | 这个岗位的任务没人能领 |
| `capability-facts` | `facts`（`executor`、可选 `provider`、`kind`：cannot / must_not / only / prefer、`subject`、可选 `scope`：值是字符串或 true / false） | 不额外排除（种子里 Owner 类的事实只当提议） |
| `routing:<租户>` | `tenant`、`order`（固定 `[capability, quota]`）、`quota_stop_percent`；可选 `min_score_percent`（0–100）+ `min_samples`，两个一起写 | 领活时不看额度线（没有读数的池照常派）；不按成绩刷人 |

## 收紧怎么判断（不带签名也能立即生效）

和上一版比：上限只降不升，执行者和主机名单只减不增，`max_action` 只降，候选只能降级、不能新增或升级（漏写的算退役），说明书不能改，能力事实只能加 cannot / must_not、不能删或改，`quota_stop_percent` 只降，成绩门槛（`min_score_percent` / `min_samples`）的任何改动都不算收紧，有效期只缩不延、生效时间不提前。判不出是收紧就按放宽处理，要签名。

## 怎么用

```bash
bash bifrost-trade-infra/scripts/agentrt/rule.sh check bifrost-trade-infra/agent-config/agentrt-rules/stg/concurrency.yaml
```

`check` 只读：平台说它会读成什么、上一版是几、是不是收紧。`sign`（Owner）先 check，再签名，再交平台；`tighten` 交一个收紧；`show <rule_id>` 看当前生效的版本。默认连 STG（`--env prod` 连 PROD），令牌是 `PLATFORM_STG_OPERATOR_TOKEN`（或 PROD 的），从环境或 `bifrost-trade-infra/.env` 读，只进权限 600 的 curl 配置文件。
