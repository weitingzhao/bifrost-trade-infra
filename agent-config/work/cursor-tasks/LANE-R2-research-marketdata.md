# LANE-R2 — research 与 market-data 代码（bifrost-research、bifrost-platform-plugin-market-data、bifrost-trade-api）

先读 `cursor-tasks/README.md`（**特别是「第 2 轮」一节：一律只推分支**）。每项的 Claim / Evidence / Fix / Ratchet 见台账 `### TD-n`。报告写到 `cursor-tasks/reports/LANE-R2.md`。分支：`cursor/r2-research`、`cursor/r2-md`、`cursor/r2-api`（起点各自 origin/main）。research 的版本号由 Claude Code 发版时再定，本道不 bump。

| 顺序 | 项 | 要做的 | 注意 |
|---|---|---|---|
| 1 | **TD-120** | 删多余的 `dagster_instance.yaml`；加校验：dagster-daemon 镜像 == '<pin>-dagster' | |
| 2 | **TD-121**（research 部分） | 必需的 Secret 键去掉 `optional: true` | 与 LANE-R1 配合，k8s 改动只在分支 |
| 3 | **TD-123** | 删约 19 条没有调用方的 research-api 路由（先逐条再确认 frontend / platform / trade-api / MCP 都没有调用）；agent / distill 触发改为「经 GraphQL 启动 Dagster job」；照 trade-api TD-40 的 test_retired_routes.py 加防线 | 改公开接口已获批；有任何调用方的路由**不删**，写进报告 |
| 4 | **TD-106** | market-data 夜间 trim 改为单飞：pg_try_advisory_lock，第二个调用回 202 already running，后台执行并把完整结果写 ops_jobs；Dagster 资产改为轮询 | Dagster 资产那一半在 research 分支 |
| 5 | **TD-119** | market-data 的 schema 迁移 Job 拆进单独的 kustomization；`make deploy` 先删旧 Job、跑迁移、等完成，再 apply base | |
| 6 | **TD-102** | 下线插件的 `/market/analytics/max-pain/compute(+history)` 与 `analytics/max_pain_math.py`；trade-api 的 `fetch_pcr_aggregate` 改读 Research 已过滤调整合约的 PCR | 改公开接口已获批；先 grep 所有调用方 |
