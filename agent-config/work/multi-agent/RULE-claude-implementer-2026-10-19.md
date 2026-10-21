# 规则草稿：`job:implementer` v2，exec:claude 进试用期（W-31 2.4「Claude 写核心代码」）

起草 2026-10-19 夜（侧线 `local_f0276607…`，统筹线程 `local_accccb4e…` 派）。这是**放宽**，要 Owner 签名；本文只起草，没签、没交平台。

## 改了什么

两份文件，内容相同：`agentrt-rules/stg/job-implementer.yaml`、`agentrt-rules/prod/job-implementer.yaml`。

| 行 | 原来（v1） | 草稿（v2） |
|---|---|---|
| `rule_version` | 1 | 2 |
| `direction` | initial | loosen |
| `effective_at` | 2026-10-15T00:00:00Z | 2026-10-20T00:00:00Z |
| exec:claude 那条候选的 `status` | `qualifying` | `probation` |

说明书（`text`）、codex 和 cursor 两条候选、`expires_at` 都不动。

平台读过（`rule.sh check`，只读，2026-10-19 23:2x），STG 和 PROD 的回答一样：`rule_version 2`、`previous_version 1`、`direction loosen`、`tightens false`、`needs_signature true`，唯一理由「candidate exec:claude|anthropic|* goes from qualifying up to probation」。

## 为什么

- Owner 10-13 定的分工：核心部分 Claude 写、Codex 只读复核。规则里早有这两条能力事实（`capability-facts` v1，STG、PROD 都签过）：`exec:claude only author_core`、`exec:codex only review_core`。
- 但领活只看 `active` 和 `probation` 的候选（`store/route.go` `readCapabilities`），claude 在实现岗是 `qualifying`，所以今天**核心类实现谁都领不到**：只有 claude 能写，而 claude 不在候选里。
- 试用期（`probation`）的效果：
  - 核心类实现（`core: true`）：只有 claude 能领（`author_core`），派给它。
  - 非核心实现：codex（`active`）排第一档；claude 和 cursor 同在第二档，只在 codex 被排除、冷却或连续失败被跳过时才轮到。
  - 门槛：`routing:dev` 没写 `min_score_percent`，所以「试用期样本不足不派核心活」那一步不生效（`competence.go` `unfit`）。以后签了成绩门槛，claude 要先攒够在岗样本才能接核心活。

## 签之前必须到位的两件（顺序不能反）

签了以后核心类任务会立刻派给 claude。如果 06 上的 agentd 还是只给 claude 只读工具的旧版，它改不了文件、交上去的分支等于基线，验收失败、返工，直到轮次和预算用完。

1. **平台**：分支 `w31/claude-implementer`（`3534454e`、`04e815f6`）合进 main、上 STG（PROD 同理）。第二个提交修了核心类任务的确定性验收派不出去的问题，没有它核心类任务停在验收那一步。
2. **06 的 agentd**：按合并后的提交构建、infra 钉住、Owner 跑 `agent-06-owner.sh update-agentd`。新版 agentd 给推分支的 claude 尝试 `Edit,Write,Bash`，只在写墙里起（主机没有墙就不起，写明原因）。

## 残留（放宽带进来的，写明）

- claude 的 Bash 命令在 Landlock 墙里，只能写本次尝试的检出、输出和 sibling；**网络是 agent 用户的主机出站规则**（自己的平台 API、Gitea、互联网 80/443、回环），和 cursor 当实现者时一样；codex 的命令没网。所以设计 v5 §6.2「同一系统用户可读」那条例外，对 claude 的命令和对 cursor 的一样成立（读得到同用户的令牌文件，命令又有网）。真正关掉要第 3 轮每槽位一个用户或虚拟机。
- 复核 422（Codex）把这一条定为 C：登记为残留，本次不改网络实现；它不是「和 codex 一样安全」——恶意仓库可以诱导 Bash 读同用户的凭据、经已放行的 HTTPS 外传，或拿凭据调用户可达的平台和 Gitea。写墙只管本地写，不管远端副作用。要关掉另立读与网络隔离的工作（第 3 轮）。

## Owner 要做的

| 什么 | 建议 | 在哪办 | 怎么回 |
|---|---|---|---|
| 签 STG 的 v2 | 签（STG 走查要它） | 你的终端，**等上面两件在 STG 到位、infra 分支合进 main 之后** | 跑下面这条；跑完在线程里说一声 |
| 签 PROD 的 v2 | STG 走查收下一件 Claude 写的核心类任务之后再签 | 你的终端 | 同上，`--env prod` |

STG（在工作区根 `/Users/vision-mac-trader/Desktop/stocks` 下跑）：

```bash
bash bifrost-trade-infra/scripts/agentrt/rule.sh sign bifrost-trade-infra/agent-config/agentrt-rules/stg/job-implementer.yaml
```

PROD：

```bash
bash bifrost-trade-infra/scripts/agentrt/rule.sh sign bifrost-trade-infra/agent-config/agentrt-rules/prod/job-implementer.yaml --env prod
```

不签：核心类实现继续没人能领，2.4「Claude 写核心代码」这一项停在这里；别的不受影响。

## 后续：计划格式里的 `core`（Owner 10-19 23:4x「核心字段 A」）

Owner 原话：「核心字段 A：计划格式加可选的 core，参谋长按规则判断哪件是核心类，路由照现有核心类规则走。」实现在平台分支 `w31/plan-core`。

**定义只有一处**：核心类 = 运行时自己的核心（设计 v5 §0 第 6 条、Owner 10-13：数据层、Redis 数据形式、内核接口、agentd、总线与叫停）。落到仓库是 `Repos` 里每个仓库新加的 `Core` 目录（`store/repos.go`）：bifrost-platform 的 `api/internal/agentrt/`、`api/internal/agentd/`、`api/cmd/agentd/`；别的仓库（infra 等）没有核心类。核心目录下的外围活（测试样板、文档、按已定接口填的页面）不算核心类。计划者和参谋长的提示都用同一段文字（`CoreText()`，从 `Repos` 生成），程序校验也读同一份目录。

| 改了什么 | 说明 |
|---|---|
| 计划格式 | 每件任务可选 `"core": true/false`，不写等于 false。原样带进提议出来的任务（`task.core`），路由照现有核心类规则走：实现只归 claude（`only author_core`），确定性验收能验，评审只归 codex（`only review_core`）。不加表、不加列、不动迁移（`task.core` 早就有） |
| 校验（计划） | 挡三种：`core` 不是 true/false（`null`、字符串、数字、对象都拒，不当 false 读）；标在没有核心类的仓库；标了 core 但任务正文没写它改的核心目录下的文件（`api/internal/agentd/…` 这类整段路径，`api/internal/agentdx/`、`vendor/api/internal/agentd/`、`api/internal/agentd.go` 都不算）。错误写明是哪件任务、为什么，进下一轮计划的任务书 |
| 校验（提议接口） | 同一个 `checkBatch`：`core` 只给 `implement` 角色、有核心目录的仓库；MCP / API 直接提议的任务也一样挡 |
| 计划者提示 | 「怎么拆」里加一条：按 Core work 一节判断，核心类标 true 并在正文写出核心目录下要改的文件；目标的仓库都没有核心类时直接说「这次没有核心类」；格式示例带 `"core": false` |
| 参谋长提示 | 答复消息的任务书带同一段 Core work；建议目标时说这件活是不是核心类。定时简报和提醒（`controllerSpec`）不加：它们不拆活 |

不做的：程序不替计划者判断「该是核心类却没标」（核心目录下的外围活不是核心类，按路径强制会误判）；这一层由参谋长按规则判断，复核和验收兜底。

复核 426（Codex）：0 A、2 B、3 C，按停线规矩收线。B1（路径按前缀匹配，`api/internal/agentd/../../x.go`、反斜杠、URL 查询都能混过）、C1（提示说文件、检查却收目录本身）、C2（同一对象里重复的键或大小写别名会让后写的覆盖前写的）、C3（错误回显整个非法值）照改，各配在旧代码上失败的用例：核心路径现在要是从仓库根起、在核心目录**下面**的完整路径；计划块里同一对象重复的键一律拒收。**B2 留给考试那条线**：本机参考判分与生产解析在新字段上的一处差异（细节在本机题集目录，TD-396）；平台判分用的是生产的解析，现有对照仍全部照预期判分。
