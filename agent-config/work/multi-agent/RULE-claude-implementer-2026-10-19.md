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
