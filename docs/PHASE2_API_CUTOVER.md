# Phase 2 — API 逐域切换（M6）

**前置**：对应域在 `bifrost-trade-api` 标 **VERIFIED**，`contract/test_{domain}_parity.py` 通过。

## 切换步骤（每域一次）

1. 启动新 API：`python scripts/run_server.py <domain>`
2. 新前端 `.env` 仅改该域 `VITE_API_*` 指向新端口
3. 跑 [PHASE1_SIGNOFF_MASTER.md](../../bifrost-trade-frontend/docs/PHASE1_SIGNOFF_MASTER.md) 对应 Batch
4. Owner 签字后更新 [MIGRATION_TRACKING.md](./MIGRATION_TRACKING.md) §4 该域

## 推荐顺序

docs → monitor → market → trading → portfolio → strategy → ops → massive → research

**禁止**：一次性切换全部 `VITE_API_*`（单变量隔离）。
