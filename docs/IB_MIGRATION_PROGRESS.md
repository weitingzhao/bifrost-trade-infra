# IB Migration Progress

> **目标**：Trade 系统全面通过 Platform IB Gateway Plugin（`redis-ib`）访问 TWS，消除 Trade 栈对 IB 的直连依赖。
>
> **两个 Operator**：
> - `bifrost-trade-socket/ib/operator/` — Trade 原有 Operator（直连 TWS，服务 Daemon 和 Celery）
> - `bifrost-platform-plugin/ib_gateway/` — Platform IB Gateway Plugin（直连 TWS，通过 `redis-ib` 对外服务）
>
> **最终状态**：Trade Socket Operator 退役；所有 IB 操作通过 Platform Gateway 的 redis-ib 完成。

## 当前状态

- **当前 Phase**: Phase 0 — 分析与对齐
- **最后更新**: 2026-07-04
- **阻塞**: 无

---

## Phase 进度

### Phase 0 — 分析与对齐 🔄

**目标**：梳理 Trade 系统当前使用 IB Operator 的所有调用点，与 Platform Gateway 已实现的 ops 对比，输出 Gap 分析报告。

**验收标准**：
- [ ] 列出 Trade Socket Operator 支持的所有 ops
- [ ] 列出 Platform Gateway 已实现的所有 ops
- [ ] 列出 Trade Worker / API 中实际使用的 ops（及调用方式）
- [ ] 输出 Gap 矩阵：哪些 ops Gateway 已有 / 缺失 / 行为差异
- [ ] 产出 docs/IB_MIGRATION_ANALYSIS.md

**改动范围**：纯分析，不改代码。

---

### Phase 1 — 读类 RPC 对齐 ⏳

**目标**：确保 Platform Gateway 完全覆盖 Trade 系统需要的所有只读 ops（行情、账户、期权链等），并验证 Trade Worker 的 `IbOperatorBarsAdapter` 可以透明切换到 Gateway。

**验收标准**：
- [ ] Gateway `protocol.py` 包含 Trade 需要的所有 read ops
- [ ] Gateway `live.py` 实现全部 read ops
- [ ] Gateway `mock.py` 实现全部 read ops（参数 + 返回结构对齐 live）
- [ ] Trade Worker `IbOperatorBarsAdapter` 验证通过 Gateway 执行 `fetch_bars_range`
- [ ] `make test` 在 plugin + trade-worker 均绿

**改动范围**：
- `bifrost-platform-plugin/src/bifrost_plugin/ib_gateway/protocol.py`
- `bifrost-platform-plugin/src/bifrost_plugin/ib_gateway/live.py`
- `bifrost-platform-plugin/src/bifrost_plugin/ib_gateway/mock.py`
- `bifrost-trade-worker/src/bifrost_worker/data/bars/` (验证，可能不需改动)

---

### Phase 2 — 写类 RPC 实现 ⏳

**目标**：在 Platform Gateway 中实现订单执行类 ops（place_order / modify_order / cancel_order），使 Trade Daemon 可以通过 redis-ib 发单。

**验收标准**：
- [ ] Gateway `protocol.py` 新增 write ops 声明
- [ ] Gateway `live.py` 实现订单执行（含回调/状态更新）
- [ ] Gateway `mock.py` 实现 mock 下单行为
- [ ] Trade Core `IbOperatorClient` 能发送 write ops 并接收结果
- [ ] Paper account E2E 验证通过

**改动范围**：
- `bifrost-platform-plugin/src/bifrost_plugin/ib_gateway/`
- `bifrost-trade-core/src/bifrost_core/ib_operator/protocol.py`（新增 ops 枚举）
- `bifrost-trade-worker/src/bifrost_worker/daemon/execution/`（适配）

---

### Phase 3 — Trade 侧切换 ⏳

**目标**：Trade Daemon 和 Worker 全部通过 Platform Gateway 操作 IB，不再使用 Trade Socket Operator。

**验收标准**：
- [ ] Daemon `execution/` 模块使用 `IbOperatorClient` → `redis-ib`（而非 Trade Socket Operator 的 stream）
- [ ] Worker Celery bars backfill 完全走 Gateway
- [ ] Trade Socket 的 `ib/operator/` 代码标记为 deprecated
- [ ] 全量 E2E：Daemon paper + Celery bars backfill

**改动范围**：
- `bifrost-trade-worker/src/bifrost_worker/daemon/execution/`
- `bifrost-trade-core/src/bifrost_core/ib_operator/config.py`（redis URL 切换）
- `bifrost-trade-socket/src/bifrost_socket/ib/operator/`（deprecation notice）

---

### Phase 4 — 清理与加固 ⏳

**目标**：移除 Trade Socket Operator 冗余代码，加固 Gateway 健壮性。

**验收标准**：
- [ ] Trade Socket Operator 代码删除或归档
- [ ] Gateway 增加重试、deadline、流量限制
- [ ] Gateway 健康探测与 Console 监控对齐
- [ ] 全量回归绿灯
- [ ] 更新 MIGRATION_TRACKING.md

---

## 决策记录

| # | 决策 | 选项 | 结论 | 日期 |
|---|------|------|------|------|
| — | （待 Phase 0 分析后产生） | — | — | — |

---

## 已知事实

### Platform Gateway 已实现的 ops（protocol.py ALL_OPS）

```
fetch_bars, fetch_bars_range, fetch_option_expirations,
fetch_option_snapshot, fetch_executions, fetch_accounts_snapshot,
ping, disconnect_all, reconnect_all
```

### Trade Socket Operator 的 ops

需要在 Phase 0 确认（从 `bifrost-trade-socket/src/bifrost_socket/ib/operator/executor.py` 提取）。

### Trade Worker 已在使用 Gateway 的模块

- `bifrost_worker/data/bars/ib_operator_transport.py` → `IbOperatorBarsAdapter`
  - 使用 ops: `ping`, `fetch_bars_range`
  - 通过 `IbOperatorClient`（bifrost-core）发送到 `ib:operator:cmd` stream

### 两个 Redis 实例

- `redis-trade`：Trade 内部 Redis（行情、daemon 状态）
- `redis-ib`：Platform IB Gateway 的 Redis（operator cmd stream、result key、health）
