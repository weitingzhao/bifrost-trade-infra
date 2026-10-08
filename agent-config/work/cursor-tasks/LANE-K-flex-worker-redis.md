# LANE-K — flex worker 的系统消息发不出去：Redis 兜底到 127.0.0.1（TD-266，flex 插件）

先读 `cursor-tasks/README.md`（第 2 轮规则：只推分支，不推 main，不发版、不 apply、不写库、不改 `TECH_DEBT.md` / `RATCHETS.md`）。报告写到 `cursor-tasks/reports/LANE-K.md`。
分支：`cursor/k-flex`（bifrost-platform-plugin-flex-query，从当前 `origin/main` 新开）。

## 背景（台账 `### TD-266`，根因已查清，不用重查）

`src/bifrost_flex_query/orchestration/notify.py:64` 用
`format_redis_url(effective_redis_dict(config, default_db=0))` 取地址；
`flex-query-worker` 的 Deployment **没有任何 `REDIS*` 环境变量**，于是兜底到 `127.0.0.1:6379`，在集群里必然 refused。

2026-10-08 10:30 UTC 那次现金作业的实测日志：

```
WARNING [bifrost_core.core.message_center] message center xadd failed
  topic=portfolio.flex_executions …: Error 111 connecting to 127.0.0.1:6379. Connection refused.
```

**消息中心有真实消费方**，所以这不是「没人要的消息」：

- `bifrost-trade-api/src/bifrost_api/monitor/routers/messages.py:32` — `_message_center_reader_loop`，阻塞 XREAD
- `bifrost-trade-frontend/src/components/MessageCenter/MessageToastStack.tsx` — 事件最终变成页面提示

现金入库本身没问题（TD-103 验收 177/0/177），丢的是信号。

## 要做

1. **先量，再改**：确认集群里其他 flex 工作负载（`flex-query-api`）是怎么拿到 Redis 地址的，以及 `effective_redis_dict` 实际读哪几个键（环境变量名、config 里的段）。把实测写进报告，再决定是加 env 还是补 config 段 —— **跟现有做法一致，不要自创第三种**。
2. 给 `flex-query-worker` 配上真实的 Redis 地址。清单改了**不要 apply**，把 apply 命令写进报告交 Claude Code。
3. **决定一件事并在报告里说明理由**：发布失败时该 `warning` 还是 `raise`？
   - 现状是 warning，而这正是它藏了这么久的原因。
   - 但 publish 失败而让整个现金入库失败也不对（数据比提示重要）。
   - 我的倾向：**保持不中断，但把失败计数变成可观测的**（比如写进该作业的结果摘要 / 一个指标），让「发不出去」不再只是一行日志。你如果有更好的做法，列出来并说明。
4. 防线：一条插件测试断言 **`notify` 在没有显式 Redis 配置时不会退到 loopback** —— 要么报错、要么明确拒绝发送并记录原因，不能静默用 `127.0.0.1`。这样下一个部署不会再默默继承这个默认值。

## 门禁

`make lint && make test`，退出码分开记录。`PYTHONPATH` 把本分支 worktree 的 `src` 放最前面。

## 边界（这条很重要）

- **不要碰 `bifrost-platform`**。platform main 必须停在 **a7ecb08**，直到那张 platform PROD 审批单发出。本道只在 flex 插件仓库里改。
- 不要碰 `bifrost-trade-api` 或 `bifrost-trade-frontend`（消费方那两处只是证据，不用改）。
- flex 插件的发布要和别的发布**严格串行**，由 Claude Code 排；本道不发版、不 apply、不起 PipelineRun。
- 不要去点或打任何审批接口，不要读 `PLATFORM_ADMIN_TOKEN` 或 `~/.config/bifrost/mcp-tokens.env`。

## 验收（Claude Code 会照跑）

部署后那次现金作业的 `flex-query-worker` 日志里没有 `Error 111 connecting to 127.0.0.1:6379`；`portfolio.flex_executions` 的事件能被 trade-api 读到。
