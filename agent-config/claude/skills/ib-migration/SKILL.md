---
name: ib-migration
description: >-
  IB Migration — Trade 系统从直连 TWS 迁移到 Platform IB Gateway (redis-ib) 的工程任务。
  Use when user says "IB migration", "Gateway RPC", "redis-ib", "Platform Gateway",
  "IB operator", "Phase N" (in IB context), or asks about Trade-to-Gateway cutover.
---

# IB Migration — Agent Skill

## When to use

- User mentions: IB migration, Gateway RPC, redis-ib, Platform Gateway, IB operator, Trade IB cutover
- User says "Phase N" in IB migration context
- User asks about Trade daemon order execution via Gateway

## Context files to read first

1. `bifrost-trade-infra/docs/IB_MIGRATION_PROGRESS.md` — 当前进度与决策
2. `bifrost-platform-plugin/src/bifrost_plugin/ib_gateway/protocol.py` — Gateway RPC 协议定义
3. `bifrost-platform-plugin/src/bifrost_plugin/ib_gateway/live.py` — Gateway 实际执行逻辑
4. `bifrost-platform-plugin/src/bifrost_plugin/ib_gateway/mock.py` — Gateway mock 实现
5. `bifrost-trade-core/src/bifrost_core/ib_operator/client.py` — Trade 侧 RPC client
6. `bifrost-trade-core/src/bifrost_core/ib_operator/protocol.py` — Trade 侧协议定义
7. ~~`bifrost-trade-socket/.../executor.py`~~ — **RETIRED**（GitHub archive / local tarball；日常勿依赖本地路径）
8. `bifrost-trade-worker/src/bifrost_worker/data/bars/ib_operator_transport.py` — Worker bars adapter

## Architecture rules

- **Gateway 是唯一 TWS 接入点**：Trade 栈不直连 TWS，所有通信通过 `redis-ib` Stream
- **双 Redis 实例**：`redis-trade`（Trade 内部）和 `redis-ib`（Platform Gateway 专用）
- **协议对齐**：两端的 `protocol.py` 定义的 `ALL_OPS` 必须一致
- **R-DV3**：Platform Agent 不得触发自动交易（写路径需 Operator 人工确认）
- **mock 必须 mirror live**：参数结构 + 返回结构完全对齐，mock 仅模拟执行结果
- **向后兼容**：Trade Core `IbOperatorClient` 的接口不变，只改底层 Redis URL 指向

## Key concepts

### 两个 Operator 的区别

| | Trade Socket Operator | Platform IB Gateway |
|---|---|---|
| 位置 | ~~`bifrost-trade-socket/ib/operator/`~~（archived） | `bifrost-platform-plugin/ib_gateway/` |
| 连接 TWS | 直连（ib_insync） | 直连（ib_insync） |
| Redis | `redis-trade` | `redis-ib` |
| 部署 | K8s Pod（Trade namespace） | K8s Pod（data namespace，Mac Mini） |
| 生命周期 | 随 Trade 栈 | 独立于 Trade 栈 |
| 最终状态 | **退役** | **唯一 IB 入口** |

### 数据流（最终状态）

```
Trade Daemon / Worker / API
  ↓ IbOperatorClient.request(op, payload)
  ↓ xadd → redis-ib:ib:operator:cmd
  ↓
Platform IB Gateway (live.py)
  ↓ handle_command(msg)
  ↓ ib_insync → TWS
  ↓ result → redis-ib:ib:operator:result:{req_id}
  ↓
Trade Daemon / Worker / API
  ↑ poll result key → response
```

## Per-phase instructions

### Phase 0: 分析与对齐

1. 契约考古：GitHub archive `weitingzhao/bifrost-trade-socket`（或本地 tarball）中 `ib/operator/executor.py` — **非工作区日常路径**
2. 读取 `bifrost-platform-plugin/src/bifrost_plugin/ib_gateway/protocol.py`，提取 `ALL_OPS`（权威）
3. Grep Trade Worker + Trade API 中 `ib_operator` / `IbOperatorClient` 的使用点
4. 对比输出 Gap 矩阵
5. 写入 `bifrost-trade-infra/docs/IB_MIGRATION_ANALYSIS.md`

**验证命令**: 无（纯文档产出）

### Phase 1: 读类 RPC 对齐

**修改文件**:
- `bifrost-platform-plugin/src/bifrost_plugin/ib_gateway/protocol.py` — 新增缺失的 read ops
- `bifrost-platform-plugin/src/bifrost_plugin/ib_gateway/live.py` — 实现
- `bifrost-platform-plugin/src/bifrost_plugin/ib_gateway/mock.py` — 实现 mock

**验证命令**:
```bash
cd /Users/vision-mac-trader/Desktop/stocks/bifrost-platform-plugin && make test
cd /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-worker && make test
```

### Phase 2: 写类 RPC 实现

**修改文件**:
- `bifrost-platform-plugin/src/bifrost_plugin/ib_gateway/protocol.py` — 新增 write ops
- `bifrost-platform-plugin/src/bifrost_plugin/ib_gateway/live.py` — 订单执行实现
- `bifrost-platform-plugin/src/bifrost_plugin/ib_gateway/mock.py` — mock 下单
- `bifrost-trade-core/src/bifrost_core/ib_operator/protocol.py` — 对齐 ALL_OPS

**验证命令**:
```bash
cd /Users/vision-mac-trader/Desktop/stocks/bifrost-platform-plugin && make test
cd /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-core && make test
```

**⚠️ 需要 Owner 决策**:
- 订单回调机制：result key（同步 poll）vs Redis Stream（异步 push）vs 两者混合
- Mock 下单行为：立即 fill vs 模拟延迟 fill
- 订单状态更新频率

### Phase 3: Trade 侧切换

**修改文件**:
- `bifrost-trade-worker/src/bifrost_worker/daemon/execution/` — 切换到 Gateway
- `bifrost-trade-core/src/bifrost_core/ib_operator/config.py` — redis URL 切换
- 配置文件 `config.yaml` — `ib_operator.redis_url` 指向 `redis-ib`

**验证命令**:
```bash
cd /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-worker && make test
cd /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-core && make test
```

### Phase 4: 清理与加固

**修改文件**:
- ~~`bifrost-trade-socket`~~ — 已 GitHub Archive + 移出 workspace（Wave 14G-F）
- `bifrost-platform-plugin/src/bifrost_plugin/ib_gateway/operator.py` — 加固（重试、超时）
- `bifrost-trade-infra/docs/MIGRATION_TRACKING.md` — 更新 IB 相关条目

**验证命令**:
```bash
# socket repo retired — do not expect local checkout
cd /Users/vision-mac-trader/Desktop/stocks/bifrost-platform-plugin && make test
cd /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-worker && make test
cd /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-core && make test
```

## Self-check commands (per repo)

| Repo | Command |
|------|---------|
| bifrost-platform-plugin | `cd bifrost-platform-plugin && make test` |
| bifrost-trade-core | `cd bifrost-trade-core && make test` |
| bifrost-trade-worker | `cd bifrost-trade-worker && make test` |
| bifrost-trade-socket | **RETIRED** — GitHub archive / tarball only |
| bifrost-trade-api | `cd bifrost-trade-api && pytest` |
